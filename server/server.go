package server

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"

	"github.com/dooferlad/next_up/importers"

	"github.com/googollee/go-socket.io"
	"github.com/gorilla/mux"
	"gopkg.in/mgo.v2"
	"gopkg.in/mgo.v2/bson"
	"gopkg.in/yaml.v2"

	"golang.org/x/net/context"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"

	calendar "google.golang.org/api/calendar/v3"
	"google.golang.org/api/gmail/v1"
)

type ServerState struct {
	cards          *mgo.Collection
	bugs           *mgo.Collection
	reviewRequests *mgo.Collection
	watchedReviews *mgo.Collection
	ciJobs         *mgo.Collection
	messages       chan string
	calendar       *mgo.Collection
	gmail          *mgo.Collection
	socket         *socketio.Socket
	cfg            Configuration
}

// collectionToJson sends all data in a Mongo collection as JSON to a client
// by writing it directly into the HTTP response.
func collectionToJson(response http.ResponseWriter, collection *mgo.Collection) {
	var data []bson.M
	query := collection.Find(nil)
	count, err := query.Count()
	if err != nil {
		panic(err)
	}
	response.Header().Set("Content-Type", "application/vnd.api+json")
	if count > 0 {
		// We don't want to encode a zero length list as "null", so we only
		// write a response if there is something to write. This makes JSON
		// decoders happier.
		err = query.All(&data)
		if err != nil {
			panic(err)
		}
		json.NewEncoder(response).Encode(&data)
	}
}

type UrlMessage struct {
	Url string
}

func (state ServerState) apiCardsHandler(response http.ResponseWriter, request *http.Request) {
	if request.Method == "POST" {
		decoder := json.NewDecoder(request.Body)
		var data UrlMessage
		err := decoder.Decode(&data)
		if err != nil {
			panic(err)
		}
		req, err := http.NewRequest("POST", data.Url, nil)
		if err != nil {
			panic(err)
		}
		//resp, err := http.PostForm(data.Url, url.Values{})
		client := &http.Client{}
		fmt.Println(state.cfg.LeankitUser)
		fmt.Println(data.Url)
		req.SetBasicAuth(state.cfg.LeankitUser, state.cfg.LeankitPass)
		resp, err := client.Do(req)
		fmt.Printf("%+v\n", resp)
		fmt.Println(err)
	} else {
		collectionToJson(response, state.cards)
	}
}

func (state ServerState) apiBugsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.bugs)
}
func (state ServerState) apiReviewRequestsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.reviewRequests)
}
func (state ServerState) apiWatchedReviewsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.watchedReviews)
}
func (state ServerState) apiCiJobs(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.ciJobs)
}
func (state ServerState) apiCalEvents(response http.ResponseWriter, request *http.Request) {
	collection := state.calendar
	var data []importers.CalEvent
	err := collection.Find(nil).All(&data)
	if err != nil {
		panic(err)
	}
	response.Header().Set("Content-Type", "application/vnd.api+json")
	if len(data) > 0 {
		// We don't want to encode a zero length list as "null", so we only
		// write a response if there is something to write. This makes JSON
		// decoders happier.
		json.NewEncoder(response).Encode(data)
	}
}
func (state ServerState) apiPing(response http.ResponseWriter, request *http.Request) {
	state.messages <- "ping"
}

// forwardUpdatesToSocketIO sends a ping to the connected clients when we
// receive a ping from a data source that something updated.
func (state *ServerState) forwardUpdatesToSocketIO() {
	server, err := socketio.NewServer(nil)
	if err != nil {
		log.Fatal(err)
	}
	server.On("connection", func(so socketio.Socket) {
		so.Join("updates")
		state.socket = &so

		so.Emit("update", "hello")
		so.On("chat message", func(msg string) {
			log.Println("emit:", so.Emit("chat message", msg))
			so.BroadcastTo("chat", "chat message", msg)
		})
		so.On("disconnection", func() {
		})
	})
	server.On("error", func(so socketio.Socket, err error) {
		log.Println("error:", err)
	})

	http.Handle("/socket.io/", server)

	for {
		_ = <-state.messages
		if state.socket != nil {
			so := *state.socket
			so.Emit("update", "db")
		}
	}
}

var router = mux.NewRouter()

type Configuration struct {
	LeankitPass        string "leankit_pass,omitempty"
	LeankitUser        string "leankit_user,omitempty"
	LpUser             string "LP_USER"
	MinBugPriority     string "MIN_BUG_PRIORITY"
	GithubUser         string "GITHUB_USER"
	GithubPass         string "GITHUB_PASS"
	ReviewBoardDomain  string "REVIEWBOARD_DOMAIN"
	ReviewBoardUser    string "REVIEWBOARD_USER"
	GoogleClientId     string "google_client_id"
	GoogleClientSecret string "google_client_secret"
}

// Run runs the web server
func Run() {
	// We spend most of our time presenting data from external sources, which
	// has already been inserted into a database (MongoDB), over our API as
	// JSON. Dial out to the database and get the collections set up.
	sess, err := mgo.Dial("localhost")
	if err != nil {
		panic(err)
	}
	defer sess.Close()
	state := ServerState{}
	db := sess.DB("next_up")
	state.cards = db.C("my_cards")
	state.bugs = db.C("my_bugs")
	state.reviewRequests = db.C("my_review_requests")
	state.watchedReviews = db.C("my_watched_reviews")
	state.ciJobs = db.C("ci_jobs")
	state.calendar = db.C("calendar")
	state.calendar.DropCollection()
	state.calendar.EnsureIndexKey("eventId")
	state.gmail = db.C("gmail")
	state.gmail.EnsureIndexKey("id")

	// We tell the web client that we have updated information by communicating
	// with it over socket.io (http://socket.io/)
	state.socket = nil

	// We are told about database updates via web hook, which dumps the messages
	// in this queue for the socket.io handler function to pick up
	state.messages = make(chan string, 1000)

	// User specific settings are stored in settings.yaml. Load and use.
	filename := "settings.yaml"
	slurp, err := ioutil.ReadFile(filename)
	if err != nil {
		log.Fatalf("Error reading %q: %v", filename, err)
	}
	err = yaml.Unmarshal(slurp, &state.cfg)
	if err != nil {
		fmt.Printf("error: %v\n", err)
	}

	// At the moment calendar updates are performed on startup. This needs to be
	// moved out into its own executable and run as a continual updater.
	oauthScopes := []string{calendar.CalendarScope, gmail.GmailModifyScope}
	config := &oauth2.Config{
		ClientID:     state.cfg.GoogleClientId,
		ClientSecret: state.cfg.GoogleClientSecret,
		Endpoint:     google.Endpoint,
		Scopes:       oauthScopes,
	}

	ctx := context.Background()
	c := importers.NewOAuthClient(ctx, config)
	//importers.GmailUpdate(state.gmail, c)

	// Paths on the web server are handled by functions. Wire them up.
	api := router.PathPrefix("/API").Subrouter()
	router.PathPrefix("/").Handler(http.FileServer(http.Dir("./static/")))

	api.HandleFunc("/cards", state.apiCardsHandler)
	api.HandleFunc("/bugs", state.apiBugsHandler)
	api.HandleFunc("/review_requests", state.apiReviewRequestsHandler)
	api.HandleFunc("/watched_reviews", state.apiWatchedReviewsHandler)
	api.HandleFunc("/ci_jobs", state.apiCiJobs)
	api.HandleFunc("/calendar", state.apiCalEvents)

	// TODO: Attach this to a services API rather than the public one!
	api.HandleFunc("/ping", state.apiPing)

	// Start the real time messaging handler
	go state.forwardUpdatesToSocketIO()

	importers.CalendarUpdate(state.calendar, c)

	http.Handle("/", router)

	log.Fatal(http.ListenAndServe(":8080", nil))
}