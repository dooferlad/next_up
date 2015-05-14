package importers

import (
	"fmt"
	"log"
	"net/http"

    "gopkg.in/mgo.v2"
	"google.golang.org/api/gmail/v1"
)

type message struct {
	size    int64
	gmailID string
	date    string // retrieved from message header
	snippet string
}

func GmailUpdate(localGmail *mgo.Collection, client *http.Client) {
	svc, err := gmail.New(client)
	if err != nil {
		log.Fatalf("Unable to create Gmail service: %v", err)
	}

	//var total int64
	//msgs := []message{}
	pageToken := ""
	req := svc.Users.Messages.List("me").Q("in:inbox label:unread").MaxResults(10)
	for {
		if pageToken != "" {
			req.PageToken(pageToken)
		}
		r, err := req.Do()
		if err != nil {
			log.Fatalf("Unable to retrieve messages: %v", err)
		}

		log.Printf("Processing %v messages...\n", len(r.Messages))

		for _, m := range r.Messages {
			msg, err := svc.Users.Messages.Get("me", m.Id).Do()
			if err != nil {
				log.Fatalf("Unable to retrieve message %v: %v", m.Id, err)
			}
            //switch
			for _, h := range msg.Payload.Headers {
				fmt.Printf("%v: %v\n", h.Name, h.Value)
			}
			fmt.Printf("%v\n", msg.Snippet)
			return
		}
		if r.NextPageToken == "" {
			break
		}
		pageToken = r.NextPageToken
	}
}
