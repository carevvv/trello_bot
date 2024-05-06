import requests
import datetime
import concurrent.futures
import requests
from configuration.config import *
import pytz



class trello_wrapper:
    def __init__(self, key, token):
        self.query = {
            "key": key,
            "token": token
        }
        self.headers = {
            "Accept": "application/json"
        }
        self.base_url = "https://api.trello.com/1/"
        self.boards_list_url = self.base_url + "boards/{}/lists"
        self.cards_url = self.base_url + "cards"
        self.lists_cards_url = self.base_url + "lists/{}/cards"
        self.card_move_url = self.base_url + "cards/{}/idList"


    def get_board_lists(self, board_id):
        response = requests.get(self.boards_list_url.format(board_id), headers=self.headers, params=self.query)
        return response.json()

    def get_trello_board_lists(self):
        url = f"https://api.trello.com/1/boards/{board_id}/lists"
        response = requests.get(url, params=self.query)
        if response.status_code == 200:
            arr = set()
            for list in response.json():
                arr.add(list['name'])
            return arr
        else:
            print(f"Ошибка при получении данных: {response.status_code}")
            return []

    def get_list_cards(self, list_id):
        response = requests.get(self.lists_cards_url.format(list_id), headers=self.headers, params=self.query)
        return response.json()
    

    def card_labels(self, card_id):
        url = f"{self.base_url}/cards/{card_id}/labels"
        response = requests.get(url, headers=self.headers, params=self.query)
        labels = response.json()
        
        member_ids = [label['name'] for label in labels]
        return member_ids
    

    def get_card_comments(self, card_id):
        url = self.cards_url + "/{}/actions".format(card_id)
        params = self.query.copy()
        params.update({"filter": "commentCard"})
        response = requests.get(url, headers=self.headers, params=params)
        comments = response.json()
        arr = []
        moscow_tz = pytz.timezone('Europe/Moscow')
        for comment in comments:
            utc_time = datetime.datetime.strptime(comment['date'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)
            local_time = utc_time.astimezone(moscow_tz)
            time = local_time.strftime('%Y-%m-%d %H:%M:%S')
            arr.append([comment['memberCreator']['fullName'], comment['data']['text'], time])
        return arr
    

    def get_full_board_info(self, board_id):
        lists = self.get_board_lists(board_id)
        card_details = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_card = {
                executor.submit(self.fetch_card_info, card, list_name=lst['name']): card
                for lst in lists for card in self.get_list_cards(lst['id'])
            }
            for future in concurrent.futures.as_completed(future_to_card):
                card = future_to_card[future]
                result = future.result()
                card_details.extend(result)

        return card_details


    def fetch_card_info(self, card, list_name):
        card_info = []
        labels = self.card_labels(card['id'])  
        for label_name in labels:
            deadline = self.format_datetime(card.get('due', None))
            if not deadline:
                deadline = None


            card_info.append({
                "title": card['name'],
                "tg_id": label_name,
                "description": card['desc'],
                "comments": self.get_card_comments(card['id']),
                "status": list_name,
                "deadline": deadline
            })
        return card_info
    
    def format_datetime(self, date_str):
        if date_str:
            moscow_tz = pytz.timezone('Europe/Moscow')
            utc_time = datetime.datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)
            local_time = utc_time.astimezone(moscow_tz)
            return local_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            return None 



    def move_card(self, board_id, from_list_name, to_list_name, card_name):
        lists = self.get_board_lists(board_id)
        from_list_id = None
        to_list_id = None
        
        for lst in lists:
            if lst['name'].lower() == from_list_name.lower():
                from_list_id = lst['id']
            elif lst['name'].lower() == to_list_name.lower():
                to_list_id = lst['id']
        
        cards = self.get_list_cards(from_list_id)
        card_id = None
        
        for card in cards:
            if card['name'].lower() == card_name.lower():
                card_id = card['id']
                break
        
        if not card_id:
            return "Card not found in the source list."
        
        url = "https://api.trello.com/1/cards/{}".format(card_id)
        params = {**self.query, "idList": to_list_id}
        
        response = requests.put(url, headers=self.headers, params=params)
        
        if response.status_code == 200:
            return "Card moved successfully."
        else:
            return "Failed to move the card. Error: {}".format(response.json())
