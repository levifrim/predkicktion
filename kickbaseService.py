import requests


class KickbaseService:
    def __init__(self, url: str, email: str, password: str):
        self.url = url
        self.email = email
        self.password = password
        self.token = None

    def authenticate(self):
        # Implement the authentication logic here
        response = requests.post(
            f"{self.url}/v4/user/login",
            json={"em": self.email, "pass": self.password},
        )
        self.token = response.json().get("tkn")
        if self.token:
            print("Authentication successful")
        else:
            raise Exception("Authentication failed: No token received")

    def get_bundesliga_id(self):
        # Implement the logic to get competitions here
        response = requests.get(
            f"{self.url}/v4/competitions",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        for comp in response.json().get("it", []):
            if comp.get("n") == "Bundesliga":
                return comp.get("i")

    def get_all_players(self, competition_id: str):
        response = requests.get(
            f"{self.url}/v4/competitions/{competition_id}/players",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return response.json()

    def get_all_teams(self, competition_id: str):
        response = requests.get(
            f"{self.url}/v4/competitions/{competition_id}/table",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return [
            {"tid": team.get("tid"), "tn": team.get("tn")}
            for team in response.json().get("it", [])
        ]

    def get_players_from_team(self, team_id: str, competition_id: str):
        response = requests.get(
            f"{self.url}/v4/competitions/{competition_id}/teams/{team_id}/teamprofile",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return response.json()

    def search_player(self, player_name: str):
        # Implement the player search logic here
        response = requests.get(
            f"{self.url}/competition/search?t={player_name}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return response.json()
