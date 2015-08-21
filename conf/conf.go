package conf

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
