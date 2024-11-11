from dave import ThumbnailDave
import datetime
import pytz


def set_first_thumbnail():

    videoid = input('Insert videoid:\n')
    videoid = videoid.strip()
    dave = ThumbnailDave()
    dave.does_first(videoid)
    print('Thumbnail set successfully!')


if __name__ == '__main__':
    set_first_thumbnail()