import os

from pymongo import MongoClient
from dotenv import load_dotenv


load_dotenv(".env.local")


MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE")


# Without MongoDB, the tools save records to local files in data/ instead
appointments_collection = None
messages_collection = None


if MONGODB_URI and MONGODB_DATABASE:

    client = MongoClient(MONGODB_URI)

    db = client[MONGODB_DATABASE]

    appointments_collection = db["appointments"]
    messages_collection = db["messages"]

else:
    print("MongoDB not configured, saving records to the data/ folder")
