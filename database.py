import pymongo
from config import MONGODB_URI

main_cluster = pymongo.MongoClient(MONGODB_URI, uuidRepresentation="standard")
database = main_cluster["main"]
db_accounts = database["accounts"]
db_users = database["users"]
