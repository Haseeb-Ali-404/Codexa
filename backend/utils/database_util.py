from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB") or "codexa"

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

users_col = db["users"]
chats_col = db["chats"]
messages_col = db["messages"]
projects_col = db["projects"]
files_col = db["files"]