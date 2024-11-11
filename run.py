from dave import ThumbnailDave
from pymongo import MongoClient
import datetime
import pytz
from bson.codec_options import CodecOptions
import traceback
from time import sleep
import json
import time
import os

BASEURL = '/home/pi/davethumbnail/'
DAVELOG = BASEURL + 'dave.json'

print('THUMBNAIL DAVE IS WORKING HERE')
# wait for internet to connect
sleep(20)


def log_to_backup_dave(logentry):
    
    if 'date' in logentry:
        logentry['date'] = logentry['date'].isoformat()
    
    if os.path.isfile(DAVELOG) and os.access(DAVELOG, os.R_OK):
        with open(DAVELOG,'r+') as file:
            file_data = json.load(file)
            file_data.append(logentry)
            file.seek(0)
            json.dump(file_data, file, indent = 4)
    else:
        with open(DAVELOG,'w') as file:
            json.dump([logentry,], file, indent = 4)
    

def log_dave(db, success, exception=None):
    
    log = {
        'date': datetime.datetime.utcnow(),
        'success': success
    }
    
    if exception:
        log['exception'] = traceback.format_exception(etype=type(exception), value=exception, tb=exception.__traceback__)
    
    try:
        db.youtube_dave_log.insert_one(log)
    except Exception as e:
        log_to_backup_dave(log)


def upload_backup_logs(db):
    
    now = str(round(time.time() * 1000))
        
    # log backup logs
    if os.path.isfile(DAVELOG) and os.access(DAVELOG, os.R_OK):
        f = open(DAVELOG)
        davelogs = json.load(f)
        f.close()
        
        for log in davelogs:
            log['date'] = datetime.datetime.fromisoformat(log['date'])
            log['backup'] = True
            
        try:
            db.youtube_dave_log.insert_many(davelogs)
        except Exception as e:
            raise e
        
        os.rename(DAVELOG, DAVELOG + now)


def run():
    
    while True:
        now = datetime.datetime.utcnow()
        now = now.astimezone(pytz.timezone('US/Pacific'))
        #now = now.replace(hour=0)
        if now.hour != 0:
            sleep(1)
            continue
        # If it's the start of a new day
        else:
            try:
                client = MongoClient('mongodb+srv://davidsniff:jnh4ONzqU4EHmdjj@firstcluster.bk8ke.mongodb.net/?retryWrites=true&w=majority&wTimeoutMS=10000')
                db = client.main.with_options(codec_options=CodecOptions(tz_aware=True, tzinfo=pytz.timezone('US/Pacific')))
            except Exception as e:
                log_dave(None, False, exception=e)
                sleep(10)
                continue
            try:
                upload_backup_logs(db)
            except Exception as e:
                sleep(10)
                continue
            #get most recent successful log
            try:
                last = db.youtube_dave_log.find({'success': True}).sort('date', -1 ).limit(1)
            except Exception as e:
                log_dave(db, False, exception=e)
                sleep(10)
                continue
            if len(list(last.clone())) == 0 or (now.date() != last[0]['date'].date()):
                try:
                    dave = ThumbnailDave()
                    dave.upload_backup_logs()
                    dave.does_it()
                except Exception as e:
                    log_dave(db, False, exception=e)
                    sleep(10)
                    continue
                log_dave(db, True)
                sleep(60*60*23)
            else: 
                sleep(60*60*23)


if __name__ == '__main__':
    run()