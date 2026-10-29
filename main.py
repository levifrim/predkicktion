import kickbaseService
import os
from dotenv import load_dotenv

BASE_URL = "https://api.kickbase.com"


if __name__ == "__main__":
    load_dotenv()
    email = os.getenv("KICKBASE_EMAIL")
    password = os.getenv("KICKBASE_PASSWORD")

    service = kickbaseService.KickbaseService(BASE_URL, email, password)
    service.authenticate()

    bundesliga_id = service.get_bundesliga_id()
    teams = service.get_all_teams(bundesliga_id)
    teams_by_name = {team["tn"]: team["tid"] for team in teams}
    stuttgart_players = service.get_players_from_team(
        teams_by_name["Stuttgart"], bundesliga_id
    )
    print(stuttgart_players)
