from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from youtube import YoutubeClient
from pymongo import MongoClient
import datetime
import pytz
from bson.codec_options import CodecOptions
import numpy as np
import traceback
import json
import time
import cv2
import os

BASEURL = '/home/pi/davethumbnail/'
TEMPFOLDER = BASEURL + 'temp/'
TEMPJPEG = TEMPFOLDER + 'temp.jpg'
TEMPPNG = TEMPFOLDER + 'temp.png'
ERRORLOG = BASEURL + 'errors.json'
THUMBNAILLOG = BASEURL + 'thumbnail.json'

THUMBNAIL_WIDTH = 1280
THUMBNAIL_HEIGHT = 720

TRIPLET_IMAGE_WIDTH = 400
TRIPLET_IMAGE_HEIGHT = 720

TRIPLET_OFFSET = 80

TRIPLET_LINE_OFFSET = 10
TRIPLET_LINE_THICKNESS = 40

# XGON Thumbnail Variables
XGON_IMAGE_WIDTH = 520
XGON_IMAGE_HEIGHT = 720

MAXIMUM_X = 28

OVERLAY = BASEURL + 'overlay.png'

DETAIL_ANGLE = 80
DETAIL_OFFSET = 60
DETAIL_COLOR_ADJUST = 35
###############################


class ThumbnailDave:
    
    def __init__(self):

        # setup mongodb
        try:
            client = MongoClient('')
            self.mongodb = client.main.with_options(codec_options=CodecOptions(tz_aware=True, tzinfo=pytz.timezone('US/Pacific')))
        except Exception as e:
            self.log_error('Failed to setup mongodb', exception=e)
            raise e
        
        # setup drive
        try:
            gauth = GoogleAuth()
            gauth.LocalWebserverAuth()
            self.drive = GoogleDrive(gauth)
        except Exception as e:
            self.log_error('Failed to setup drive', exception=e)
            raise e
        
        # setup youtube
        try:
            self.youtube = YoutubeClient()
        except Exception as e:
            self.log_error('Failed to setup youtube', exception=e)
            raise e


    def log_to_backup(self, logtype, logentry):
    
        if logtype == 'error':
            filename = ERRORLOG
        elif logtype == 'thumbnail':
            filename = THUMBNAILLOG
        else:
            return
        
        if 'date' in logentry:
            logentry['date'] = logentry['date'].isoformat()
        
        if os.path.isfile(filename) and os.access(filename, os.R_OK):
            with open(filename,'r+') as file:
                file_data = json.load(file)
                file_data.append(logentry)
                file.seek(0)
                json.dump(file_data, file, indent = 4)
        else:
            with open(filename,'w') as file:
                json.dump([logentry,], file, indent = 4)


    def upload_backup_logs(self):
        
        now = str(round(time.time() * 1000))
        
        # log backup logs
        if os.path.isfile(ERRORLOG) and os.access(ERRORLOG, os.R_OK):
            f = open(ERRORLOG)
            backuperrorlogs = json.load(f)
            f.close()
            
            for log in backuperrorlogs:
                log['date'] = datetime.datetime.fromisoformat(log['date'])
                log['backup'] = True
            
            try:
                self.mongodb.errors.insert_many(backuperrorlogs)
            except Exception as e:
                raise e
            
            os.rename(ERRORLOG, ERRORLOG + now)
            
        # log backup logs
        if os.path.isfile(THUMBNAILLOG) and os.access(THUMBNAILLOG, os.R_OK):
            f = open(THUMBNAILLOG)
            thumbnaillogs = json.load(f)
            f.close()
            
            for log in thumbnaillogs:
                log['date'] = datetime.datetime.fromisoformat(log['date'])
                log['backup'] = True
                
            try:
                self.mongodb.youtube_thumbnail_log.insert_many(thumbnaillogs)
            except Exception as e:
                raise e
            
            os.rename(THUMBNAILLOG, THUMBNAILLOG + now)
            
    
    def log_error(self, message, exception=None):
        
        error = {
            'date': datetime.datetime.utcnow(),
            'message': message,
            'origin': 'thumbnail_dave'
        }
        
        if exception:
            error['exception'] = traceback.format_exception(etype=type(exception), value=exception, tb=exception.__traceback__)
        
        try:
            self.mongodb.errors.insert_one(error)
        except Exception as e:
            error.pop('_id', None)
            self.log_to_backup('error', error)
            raise e


    def get_triplets(self, folderid, daysold):
        try:
            images = self.drive.ListFile({'q': "'{}' in parents and trashed=false".format(folderid)}).GetList()
        except Exception as e:
            self.log_error('Failed to list drive images', e)
            raise e
        images = sorted([i for i in images if i['mimeType'] == 'image/png'], key=lambda i: i['title'])

        if len(images) < 1:
            return None

        stills = []

        for i in range(3):
            index = (daysold + i) % len(images)
            try:
                gfile = self.drive.CreateFile({'id': images[index]['id']})
                gfile.GetContentFile(TEMPPNG)
            except Exception as e:
                self.log_error('Failed to load drive image', e)
                raise e
            still = {
                'title': images[index]['title'],
                'drive_id': images[index]['id'],
                'file': cv2.imread(TEMPPNG)
            }

            stills.append(still)

        return stills
    
    
    def get_videos(self, now):

        oneday = now - datetime.timedelta(days=1)
        
        try:
            videos = list(self.mongodb.youtube_uploads.find( {"release_date": {"$lt": oneday}} ))
        except Exception as e:
            self.log_error('Failed to load videos from mongodb', e)
            raise e
        
        return videos


    def get_color(self):
        
        try:
            color = self.mongodb.settings.find_one( {"name": 'youtube_thumbnail_detail_color'} )
        except Exception as e:
            self.log_error('Failed to load colors from mongodb', e)
            raise e
        
        return color['value']
    
        
    def post_thumbnail_log(self, videoid, videotitle, stills, color, daysold):

        post = {'youtube_video_id': videoid,
                'youtube_video_title': videotitle,
                'stills': stills,
                'color': color,
                'daysold': daysold,
                'date': datetime.datetime.utcnow()}
        
        try:
            self.mongodb.youtube_thumbnail_log.insert_one(post)
        except Exception as e:
            post.pop('_id', None)
            self.log_to_backup('thumbnail', post)
    
    
    def update_thumbnail(self, videoid):
        try:
            self.youtube.set_thumbnail(videoid, TEMPJPEG)
        except Exception as e:
            self.log_error('Failed to update thumbnail', e)
            raise e


    def set_triplet_thumbnail(self, video, today, basecolor, first=False):

        if first:
            daysold = 0
        else:
            daysold = today - video['release_date']
            daysold = daysold.days
        
        thumbnail = np.zeros((THUMBNAIL_HEIGHT,THUMBNAIL_WIDTH,3), np.uint8)
        try:
            stills = self.get_triplets(video['drive_stills_folder_id'], daysold)
        except Exception as e:
            self.log_error('Failed to access stills for "%s"' % video['youtube_video_title'], e)
            raise e
        
        if not stills:
            self.log_error('No stills available for "%s"' % video['youtube_video_title'], e)
            raise Exception

        o = TRIPLET_OFFSET
        cleanStills = [] #for logging later

        for still in stills:
            thumbnail[0:THUMBNAIL_HEIGHT, o:o+TRIPLET_IMAGE_WIDTH] = still['file']
            o += TRIPLET_IMAGE_WIDTH
            cleanStills.append( { k: still[k] for k in ['title', 'drive_id'] })

        if 'thumbnail_detail_color' in video and type(video['thumbnail_detail_color'] is list):
            color = video['thumbnail_detail_color']
        else:
            color = basecolor
        
        lineX = TRIPLET_LINE_OFFSET + int(TRIPLET_LINE_THICKNESS/2)

        cv2.line(thumbnail, (lineX, 0), (lineX, THUMBNAIL_HEIGHT), color, TRIPLET_LINE_THICKNESS)
        cv2.imwrite(TEMPJPEG, thumbnail)
        
        if first:
            cv2.imwrite('./thumbnail.jpg', thumbnail) 
        
        self.update_thumbnail(video['youtube_video_id'])
        self.post_thumbnail_log(video['youtube_video_id'], video['youtube_video_title'], cleanStills, color, daysold)
    
    
    def does_it(self):
    
        today = datetime.datetime.utcnow()
        today = today.astimezone(pytz.timezone('US/Pacific'))
        videos = self.get_videos(today)
        basecolor = self.get_color()
        
        for video in videos:
            try:
                self.set_triplet_thumbnail(video, today, basecolor)
            except Exception as e:
                self.log_error('Failed to set thumbnail for "%s"' % video['youtube_video_title'], e)
    

    def does_first(self, videoid):

        try:
            video = self.mongodb.youtube_uploads.find_one( {"youtube_video_id": videoid})
        except Exception as e:
            print('Failed to load video from mongodb')
            raise e

        color = self.get_color()
        
        self.set_triplet_thumbnail(video, None, color, first=True)


    #Deprecated
    def get_colors(self):
        
        try:
            colors = self.mongodb.settings.find_one( {"name": 'youtube_thumbnail_colors'} )
        except Exception as e:
            self.log_error('Failed to load colors from mongodb', e)
            raise e
        
        return colors['value']

    #Deprecated
    def get_xgon_image(self, folderid, daysold):
        try:
            images = self.drive.ListFile({'q': "'{}' in parents and trashed=false".format(folderid)}).GetList()
        except Exception as e:
            self.log_error('Failed to list drive images', e)
            raise e
        images = sorted([i for i in images if i['mimeType'] == 'image/jpeg'], key=lambda i: i['title'])
        index = daysold % len(images)
        try:
            gfile = self.drive.CreateFile({'id': images[index]['id']})
            gfile.GetContentFile(TEMPJPEG)
        except Exception as e:
            self.log_error('Failed to load drive image', e)
            raise e
        image = {
            'title': images[index]['title'],
            'id': images[index]['id'],
            'file': cv2.imread(TEMPJPEG)
        }
        return image

    #Deprecated
    def draw_xgon(self, x):
        
        xgon = np.zeros((THUMBNAIL_HEIGHT,THUMBNAIL_WIDTH,3), np.uint8)
        xgon[:,:,:] = 255
        R = 350
        
        if x == 6:
            R = 370
        
        if x != 1000:
            theta = np.pi+(x-2)*np.pi/x
            a = 2*R*np.sin(np.pi/x)
            r = R*np.cos(np.pi/x)
            rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]], np.longdouble)
            vector = np.array([a, 0], np.longdouble)
            
            if x == 7:
                adjustment = 10
            elif x == 9:
                adjustment = 7
            elif x == 11:
                adjustment = 5
            elif x == 13:
                adjustment = 3
            else:
                adjustment = 0
                
            currentpoint = np.array([THUMBNAIL_WIDTH/2-a/2, THUMBNAIL_HEIGHT-(THUMBNAIL_HEIGHT-2*r)/2 + adjustment], np.longdouble)
            points = np.array([currentpoint.copy(), ], np.longdouble)
            for i in range(x):
                currentpoint += vector
                points = np.append(points, [currentpoint.copy()], axis = 0)
                vector = np.dot(rot, vector)
            points = points.astype(np.int32)
            xgon = cv2.fillPoly(xgon, [points], (0,0,0))
        else:
            xgon = cv2.circle(xgon,(round(THUMBNAIL_WIDTH/2), round(THUMBNAIL_HEIGHT/2)), R, (0,0,0), -1)
        
        
        xgon = cv2.cvtColor(xgon, cv2.COLOR_BGR2GRAY)
        (T, mask) = cv2.threshold(xgon, 1, 255, cv2.THRESH_BINARY)
        
        return mask

    #Deprecated
    def add_overlay(self, image):
        overlay = cv2.imread(OVERLAY)
        
        a = image.astype(float)/255
        b = overlay.astype(float)/255
        
        out = np.zeros_like(a)
        mask = a > 0.5
        
        out[mask] = (1-(1-2*(a-0.5))*(1-b))[mask]        
        out[~mask] = (2*a*b)[~mask]
        out = (out*255).astype(np.uint8)
        
        return out
    
    #Deprecated
    def add_arrows_detail(self, image, color):
        
        darkercolor = [0,0,0]
        for i, c in enumerate(color):
            if c - DETAIL_COLOR_ADJUST < 0:
                darkercolor[i] = 0
            else:
                darkercolor[i] = c - DETAIL_COLOR_ADJUST
        darkercolor = tuple(darkercolor)
            
        leftgoingpoint = (int(THUMBNAIL_WIDTH/2), int(THUMBNAIL_HEIGHT/2))
        rightgoingpoint = (int(THUMBNAIL_WIDTH/2), int(THUMBNAIL_HEIGHT/2))
            
        for x in range(10):
            cv2.line(image, leftgoingpoint, (leftgoingpoint[0] - DETAIL_ANGLE, 0), darkercolor, 10)
            cv2.line(image, leftgoingpoint, (leftgoingpoint[0] - DETAIL_ANGLE, THUMBNAIL_HEIGHT), darkercolor, 10)
            leftgoingpoint = (leftgoingpoint[0] - DETAIL_OFFSET, leftgoingpoint[1])
            
            cv2.line(image, rightgoingpoint, (rightgoingpoint[0] + DETAIL_ANGLE, 0), darkercolor, 10)
            cv2.line(image, rightgoingpoint, (rightgoingpoint[0] + DETAIL_ANGLE, THUMBNAIL_HEIGHT), darkercolor, 10)
            rightgoingpoint = (rightgoingpoint[0] + DETAIL_OFFSET, rightgoingpoint[1])
            
        return image

    #Deprecated
    def set_xgon_thumbnail(self, video, today, basecolors, first=False):

        if first:
            daysold = 0
        else:
            daysold = today - video['release_date']
            daysold = daysold.days
        
        background = np.zeros((THUMBNAIL_HEIGHT,THUMBNAIL_WIDTH,3), np.uint8)
        try:
            image = self.get_xgon_image(video['drive_thumbnail_folder_id'], daysold)
        except Exception as e:
            self.log_error('Failed to access thumbnail images for "%s"' % video['youtube_video_title'], e)
            raise e
        
        xoff = round((THUMBNAIL_WIDTH-XGON_IMAGE_WIDTH)/2)
        background[0:THUMBNAIL_HEIGHT, xoff:xoff+XGON_IMAGE_WIDTH] = image['file']

        if 'thumbnail_colors' in video and type(video['thumbnail_colors'] is list):
            colors = video['thumbnail_colors']
        else:
            colors = basecolors
        
        startindex = video.get('thumbnail_color_start_index',0)
        index = (startindex + daysold) % len(colors)
        color = colors[index]
        cover = np.zeros((THUMBNAIL_HEIGHT,THUMBNAIL_WIDTH,3), np.uint8)
        cover[:,:,:] = color
        cover = self.add_arrows_detail(cover, color)
        
        x = daysold + 6
        # 1000 triggers drawing of circle
        if x >= MAXIMUM_X:
            x = 1000
        
        mask = self.draw_xgon(x)
        cover = cv2.bitwise_and(cover, cover, mask=mask)
        thumbnail = background + cover
        cv2.imwrite(TEMPJPEG, thumbnail)
        
        if first:
            cv2.imwrite('./thumbnail.jpg', thumbnail) 
        
        self.update_thumbnail(video['youtube_video_id'])
        self.post_thumbnail_log(video['youtube_video_id'], video['youtube_video_title'], { 'title': image['title'], 'drive_id': image['id'] }, color, daysold)
