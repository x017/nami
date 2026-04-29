import threading
import time 
from mutagen.easyid3 import EasyID3
import vlc 
from mutagen import mp3



class Player:
    def __init__(self):
        self.current_music = None
        self.player = None
        self.is_playing = threading.Event()
    def load(self,new_music):
        self.current_music = new_music
        self.player = vlc.MediaPlayer(self.current_music) 

        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached,self._on_playback_end)

    def play(self):
        if self.player:
            self.is_playing.set()
            self.player.play()
        else:
            return 0

    def stop(self):
        if self.player:
            self.player.stop()

    def pause(self):
        self.player.pause()


    def get_info(self):
        if self.current_music:
            self.metadata = mp3.MP3(self.current_music)
            self.info = EasyID3(self.current_music)

            title = self.info.get("title", ["Unknown"])[0]
            artist = self.info.get("artist", ["Unknown"])[0]
            album = self.info.get("album", ["Unknown"])[0]
            genre = self.info.get("genre", ["Unknown"])[0]
            date = self.info.get("date", ["Unknown"])[0] 
            length = self.metadata.info.length

            info = {
                    'length':f"{length:.2f}",
                    'title':title,
                    'artist':artist,
                    'album':album,
                    'genre':genre,
                    'date':date,
                    }
            return info 
        else:
            return 0

    def get_current_position(self):
        position = self.player.get_position()    
        percent = position * 100
        return percent

    def seek(self,position):
        pass

    def _on_playback_end(self, event):
        """Called by VLC when the media finishes."""
        self.is_playing.clear()
        # Optionally trigger next song, stop UI spinner, etc.
    def wait_until_finished(self):
        while player.is_playing.is_set():
            time.sleep(0.1)



