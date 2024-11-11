import os
import pickle
from googleapiclient.http import MediaFileUpload
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


class YoutubeClient():

    def __init__(self):
        # The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
        # the OAuth 2.0 information for this application, including its client_id and
        # client_secret. You can acquire an OAuth 2.0 client ID and client secret from
        # the {{ Google Cloud Console }} at
        # {{ https://cloud.google.com/console }}.
        # Please ensure that you have enabled the YouTube Data API for your project.
        # For more information about using OAuth2 to access the YouTube Data API, see:
        #   https://developers.google.com/youtube/v3/guides/authentication
        # For more information about the client_secrets.json file format, see:
        #   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
        client_secrets_file = 'client_secrets.json'
        credentials_file = 'credentials.pickle'

        # This OAuth 2.0 access scope allows for full read/write access to the
        # authenticated user's account.
        scopes = ['https://www.googleapis.com/auth/youtubepartner']
        api_service_name = 'youtube'
        api_version = 'v3'
        
        credentials = None
        
        if os.path.exists(credentials_file):
            #print('Loading Youtube Credentials from File...')
            with open(credentials_file, 'rb') as token:
                credentials = pickle.load(token)

        # If there are no valid credentials available, then either refresh the token or log in.
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                #print('Refreshing Access Token...')
                credentials.refresh(Request())
            else:
                #print('Fetching New Tokens...')
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secrets_file,
                    scopes=scopes
                )

                flow.run_local_server(port=8080)
                credentials = flow.credentials

                # Save the credentials for the next run
                with open(credentials_file, 'wb') as f:
                    #print('Saving Credentials for Future Use...')
                    pickle.dump(credentials, f)
            
        self.youtube = build(api_service_name, api_version, credentials = credentials)
    

    def set_thumbnail(self, videoid, thumbnail):
        
        request = self.youtube.thumbnails().set(
            videoId=videoid,
            media_body = MediaFileUpload(thumbnail)
        )
        response = request.execute()

        return response