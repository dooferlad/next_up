package importers

import (
	"log"
	"net/http"
	"time"

	"github.com/dooferlad/next_up/storage"

	"gopkg.in/mgo.v2"
	"gopkg.in/mgo.v2/bson"

	calendar "google.golang.org/api/calendar/v3"
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
		log.Fatalf("Unable to create Calendar service: %v", err)
	}

	listRes, err := svc.CalendarList.List().Fields("items/id").Do()
	if err != nil {
		log.Fatalf("Unable to retrieve list of calendars: %v", err)
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
                m.T =  float64(time.Now().Unix())
				localCalendar.Insert(m)
			}
		}
	}
}
