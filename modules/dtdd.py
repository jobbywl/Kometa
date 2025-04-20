from modules import util
from modules.util import Failed
from contextlib import closing
from datetime import datetime

import sqlite3
import json

logger = util.logger


builders = []
base_url = "https://www.doesthedogdie.com"

class DoesTheDogDieTrigger:
    def __init__(self,topic):
        if "TopicId" in topic:
            self.topicId = topic["TopicId"]
        if "yesSum" in topic:
            self.yesSum = topic["yesSum"]
        else:
            self.yesSum = 0
        if "noSum" in topic:
            self.noSum = topic["noSum"]
        else:
            self.noSum = 0
        if "isVerifiedYes" in topic:
            self.isVerifiedYes = topic["isVerifiedYes"]
        else:
            self.isVerifiedYes = False
        if "name" in topic["topic"]:
            self.name = topic["topic"]["name"]
        if "notName" in topic["topic"]:
            self.notName = topic["topic"]["notName"]
        if "categoryId" in topic["topic"]["TopicCategory"]:
            self.categoryId = topic["topic"]["TopicCategory"]["categoryId"]
        if "category" in topic["topic"]["TopicCategory"]:
            self.category = topic["topic"]["TopicCategory"]["category"]



class DoesTheDogDie:
    def __init__(self, requests, cache, params):
        self.requests = requests
        self.token = params["token"]
        self.cache = cache
        self.headers = {"X-API-KEY":self.token,"Accept":"application/json"}
        self.__create_cache()

    def get_media_id(self,imdb_id):
        if imdb_id == None:
            return -1

        cache_result = self.__query_media_id(imdb_id)
        if  len(cache_result) > 0:
             return cache_result["dtdd_media_id"]
        url = base_url + "/dddsearch?imdb=" +imdb_id
        r = self.requests.get(url,headers=self.headers)
        if(r.status_code == 200):
            json = r.json()
            if len(json["items"]) > 0:
                created_at = r.json()["items"][0]["createdAt"]
                media_id = r.json()["items"][0]["id"]
                self.__update_media_id(imdb_id,created_at,media_id)
                return media_id
        else:
            logger.error(f"Could not find data for {imdb_id} on Does the Dog Die!")
        return -1

    def get_topics(self, media_id):
        if media_id == -1:
            return []
        cache_result = self.__query_topics(media_id)
        if  len(cache_result) > 0:
             return cache_result

        r = self.requests.get(f"{base_url}/media/{media_id}",headers=self.headers)
        if r.status_code == 200:
            topicList = []

            for topic in r.json()["topicItemStats"]:
                self.__update_topic(media_id,topic)
                topicList.append(DoesTheDogDieTrigger(topic))
            return topicList
        return []

    def clear_cache(self):
        with sqlite3.connect(self.cache.cache_path) as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.cursor()) as cursor:
                cursor.execute("""
                DROP TABLE IF EXISTS dtdd_topics
                """)
                cursor.execute("""
                DROP TABLE IF EXISTS dtdd_media
                """)
        self.create_cache()

    def __update_topic(self,media_id,dtdd_json):
        try:
            if "TopicId" in dtdd_json:
                topicId = dtdd_json["TopicId"]
            if "ItemId" in dtdd_json:
                itemId = dtdd_json["ItemId"]
            if "topicItemId" in dtdd_json:
                topicItemId = dtdd_json["topicItemId"]
            else:
                topicItemId = f"{topicId}-{itemId}"
            
            with sqlite3.connect(self.cache.cache_path) as connection:
                connection.row_factory = sqlite3.Row
                with closing(connection.cursor()) as cursor:
                    cursor.execute(f"INSERT OR IGNORE INTO dtdd_topics(dtdd_media_id, dtdd_topic_id, dtdd_topic_item_id, dtdd_json, last_changed) VALUES(?, ?, ?, ?, ?)", (media_id,topicId,topicItemId,json.dumps(dtdd_json),datetime.now().strftime("%Y-%m-%d")))
                    cursor.execute(f"UPDATE dtdd_topics set dtdd_json = ?, last_changed = ? where dtdd_topic_item_id = ?", (json.dumps(dtdd_json),datetime.now().strftime("%Y-%m-%d"),topicItemId))
        except:
            logger.error(f"Error caching topic {dtdd_json['topic']['name']} for dtdd media id {media_id}")

    def __update_media_id(self,imdb_id,created_at,media_id):
        with sqlite3.connect(self.cache.cache_path) as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.cursor()) as cursor:
                cursor.execute(f"INSERT OR IGNORE INTO dtdd_media(imdb_id, dtdd_created_at, dtdd_media_id, last_changed) VALUES(?, ?, ?, ?)", (imdb_id, created_at,media_id,datetime.now().strftime("%Y-%m-%d")))

    def __query_media_id(self,imdb_id):
        with sqlite3.connect(self.cache.cache_path) as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.cursor()) as cursor:
                cursor.execute(f"""
                SELECT
                    imdb_id,
                    dtdd_created_at,
                    dtdd_media_id
                FROM dtdd_media
                WHERE 
                    imdb_id = ?
                """, (imdb_id,))
                result = cursor.fetchone()
        if result:
            return result
        else:
            return []

    def __query_topics(self,media_id,max_age = 30):
        with sqlite3.connect(self.cache.cache_path) as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.cursor()) as cursor:
                cursor.execute("""
                SELECT
                    dtdd_json
                FROM dtdd_topics
                WHERE 1=1
                    AND julianday('now') - julianday(last_changed) < ?
                    AND dtdd_media_id = ?
                """,(max_age,media_id))
                result = cursor.fetchall()
        if result:
            return list(map(lambda v: DoesTheDogDieTrigger(json.loads(v["dtdd_json"])),result))
        else:
            return []

    def __create_cache(self):
        with sqlite3.connect(self.cache.cache_path) as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.cursor()) as cursor:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS dtdd_topics(
                    key INTEGER PRIMARY KEY,
                    dtdd_topic_item_id TEXT UNIQUE,
                    dtdd_topic_id INTEGER,
                    dtdd_media_id INTEGER,
                    dtdd_json TEXT,
                    last_changed TEXT)
                """)

                cursor.execute("""
                CREATE TABLE IF NOT EXISTS dtdd_media(
                    key INTEGER PRIMARY KEY,
                    imdb_id TEXT,
                    dtdd_created_at TEXT,
                    dtdd_media_id INTEGER UNIQUE,
                    last_changed TEXT)
                """)