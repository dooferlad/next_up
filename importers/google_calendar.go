package importers

import (
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"time"

	"github.com/dooferlad/next_up/conf"
	"github.com/dooferlad/next_up/storage"

	"gopkg.in/mgo.v2"
	"gopkg.in/mgo.v2/bson"
	"gopkg.in/yaml.v2"

	"golang.org/x/net/context"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"

	"google.golang.org/api/calendar/v3"
	"google.golang.org/api/gmail/v1"
)

type CalEvent struct {
	HangoutLink string `bson:"hangoutLink"`
	EventId     string `bson:"eventId"`
	Start       string `bson:"start"`
	End         string `bson:"end"`
	Summary     string `bson:"summary"`
	Etag        string `bson:"etag"`
	HtmlLink    string `bson:"htmlLink"`
}

func CalendarUpdate(localCalendar *mgo.Collection, client *http.Client) {

	svc, err := calendar.New(client)
	if err != nil {
		log.Printf("Unable to create Calendar service: %v\n", err)
	}

	listRes, err := svc.CalendarList.List().Fields("items/id").Do()
	if err != nil {
		log.Printf("Unable to retrieve list of calendars: %v\n", err)
	}

	if len(listRes.Items) > 0 {
		id := "james.tunnicliffe@canonical.com"
		now := time.Now().Format(time.RFC3339)
		tomorrow := time.Now().Add(time.Hour * 24).Format(time.RFC3339)
		res, err := svc.Events.List(id).
			Fields("items(hangoutLink,id,start,end,summary,etag,htmlLink)").
			SingleEvents(true).
			TimeMin(now).
			TimeMax(tomorrow).
			Do()
		if err != nil {
			log.Fatalf("Unable to retrieve calendar events list: %v", err)
		}

		for _, v := range res.Items {
			event := CalEvent{
				HangoutLink: v.HangoutLink,
				EventId:     v.Id,
				Start:       v.Start.DateTime,
				End:         v.End.DateTime,
				Summary:     v.Summary,
				Etag:        v.Etag,
				HtmlLink:    v.HtmlLink,
			}
			changeInfo, err := localCalendar.Upsert(
				bson.M{"eventId": v.Id, "etag": v.Etag},
				&event)
			if err != nil {
				panic(err)
			}
			if changeInfo.Updated > 0 {
				var m storage.Message
				m.K = "update_time"
				m.V = ""
				m.T = float64(time.Now().Unix())
				localCalendar.Insert(m)
			}
		}
	}
}

// GetGoogleCalendar loggs into your google calendar and downloads entries
// into the mongo collection "calendar"
func GetGoogleCalendar() {
	// We spend most of our time presenting data from external sources, which
	// has already been inserted into a database (MongoDB), over our API as
	// JSON. Dial out to the database and get the collections set up.
	sess, err := mgo.Dial("localhost")
	if err != nil {
		panic(err)
	}
	defer sess.Close()
	db := sess.DB("next_up")
	caldb := db.C("calendar")
	caldb.EnsureIndexKey("eventId")

	// User specific settings are stored in settings.yaml. Load and use.
	filename := "settings.yaml"
	slurp, err := ioutil.ReadFile(filename)
	if err != nil {
		log.Fatalf("Error reading %q: %v", filename, err)
	}

	var config conf.Configuration

	err = yaml.Unmarshal(slurp, &config)
	if err != nil {
		fmt.Printf("error: %v\n", err)
	}

	// At the moment calendar updates are performed on startup. This needs to be
	// moved out into its own executable and run as a continual updater.
	oauthScopes := []string{calendar.CalendarScope, gmail.GmailModifyScope}
	authConfig := &oauth2.Config{
		ClientID:     config.GoogleClientId,
		ClientSecret: config.GoogleClientSecret,
		Endpoint:     google.Endpoint,
		Scopes:       oauthScopes,
	}

	ctx := context.Background()
	c := NewOAuthClient(ctx, authConfig)

	CalendarUpdate(caldb, c)
}
