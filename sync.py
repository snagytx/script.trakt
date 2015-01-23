# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import utilities
from utilities import Debug, notification
import copy
import datetime

progress = xbmcgui.DialogProgress()

class Sync():

	def __init__(self, show_progress=False, run_silent=False, library="all", api=None):
		self.traktapi = api
		self.show_progress = show_progress
		self.run_silent = run_silent
		self.library = library
		if self.show_progress and self.run_silent:
			Debug("[Sync] Sync is being run silently.")
		self.sync_on_update = utilities.getSettingAsBool('sync_on_update')
		self.notify = utilities.getSettingAsBool('show_sync_notifications')
		self.notify_during_playback = not (xbmc.Player().isPlayingVideo() and utilities.getSettingAsBool("hide_notifications_playback"))
		self.simulate = utilities.getSettingAsBool('simulate_sync')
		if self.simulate:
			Debug("[Sync] Sync is configured to be simulated.")

		_opts = ['ExcludePathOption', 'ExcludePathOption2', 'ExcludePathOption3']
		_vals = ['ExcludePath', 'ExcludePath2', 'ExcludePath3']
		self.exclusions = []
		for i in range(3):
			if utilities.getSettingAsBool(_opts[i]):
				_path = utilities.getSetting(_vals[i])
				if _path != "":
					self.exclusions.append(_path)

	def isCanceled(self):
		if self.show_progress and not self.run_silent and progress.iscanceled():
			Debug("[Sync] Sync was canceled by user.")
			return True
		elif xbmc.abortRequested:
			Debug('Kodi abort requested')
			return True
		else:
			return False

	def updateProgress(self, *args, **kwargs):
		if self.show_progress and not self.run_silent:
			kwargs['percent'] = args[0]
			progress.update(**kwargs)

	def checkExclusion(self, file):
		for _path in self.exclusions:
			if file.find(_path) > -1:
				return True
		return False

	''' begin code for episode sync '''
	def traktLoadShows(self):
		self.updateProgress(10, line1=utilities.getString(1485), line2=utilities.getString(1486))

		Debug('[Episodes Sync] Getting episode collection from trakt.tv')
		traktShows = {}
		traktShows = self.traktapi.getShowsLibrary(traktShows)
		traktShows = self.traktapi.getShowsWatched(traktShows)
		traktShows = traktShows.items()
		if not isinstance(traktShows, list):
			Debug("[Episodes Sync] Invalid trakt.tv show list, possible error getting data from trakt, aborting trakt.tv collection update.")
			return False

		self.updateProgress(12, line2=utilities.getString(1487))

		shows = {}
		shows['shows'] = []
		for key, show in traktShows:
			#show = vars(show)
			#will keep the data in python structures - just like the KODI response
			show = show.to_info()
			
			shows['shows'].append(show)


		return shows

	def xbmcLoadShowList(self):
		Debug("[Episodes Sync] Getting show data from Kodi")
		data = utilities.xbmcJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetTVShows', 'params': {'properties': ['title', 'imdbnumber', 'year']}, 'id': 0})
		if not data:
			Debug("[Episodes Sync] xbmc json request was empty.")
			return None
		
		if not 'tvshows' in data:
			Debug('[Episodes Sync] Key "tvshows" not found')
			return None

		shows = data['tvshows']
		Debug("[Episodes Sync] Kodi JSON Result: '%s'" % str(shows))

		# reformat show array
		for show in shows:
			show['ids'] = {}
			show['ids']['tvdb'] = ""
			show['ids']['imdb'] = ""
			id = show['imdbnumber']
			if id.startswith("tt"):
				show['ids']['imdb'] = id
			if id.isdigit():
				show['ids']['tvdb'] = id
			del(show['imdbnumber'])
			del(show['label'])
		Debug("Shows finished %s" % shows)
		return shows

	def xbmcLoadShows(self):
		self.updateProgress(1, line1=utilities.getString(1480), line2=utilities.getString(1481))

		tvshows = self.xbmcLoadShowList()
		if tvshows is None:
			return None
		Debug("tvshows %s" % tvshows)
		self.updateProgress(2, line2=utilities.getString(1482))
		result = {}
		result['shows'] = []
		i = 0
		x = float(len(tvshows))
		Debug("[Episodes Sync] Getting episode data from Kodi")
		for show_col1 in tvshows:
			Debug("show_col1 %s" % show_col1)

			show = {'title': show_col1['title'], 'ids': {'tvdb': show_col1['ids']['tvdb']}, 'year': show_col1['year'], 'seasons': []}

			data = utilities.xbmcJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': show_col1['tvshowid'], 'properties': ['season', 'episode', 'playcount', 'uniqueid', 'file']}, 'id': 0})
			if not data:
				Debug("[Episodes Sync] There was a problem getting episode data for '%s', aborting sync." % show['title'])
				return None
			if not 'episodes' in data:
				Debug("[Episodes Sync] '%s' has no episodes in Kodi." % show['title'])
				continue				

			episodes = []
			a_episodes = {}
			previous_season=0;   
			seasons = []
			for episode in data['episodes']:
				watched = 0;
				if episode['playcount'] > 0:
					watched = 1
				while not episode['season'] in a_episodes :
					s_no = episode['season']
					a_episodes[s_no] = []
				s_no = episode['season']
				a_episodes[s_no].append({ 'number': episode['episode'], 'collected_at': datetime.datetime.now().isoformat(), 'ids': { 'tvdb': episode['uniqueid']['unknown'], 'episodeid' : episode['episodeid']}, 'watched': watched })
				
			for episode in a_episodes:
				seasons.append({'number': episode, 'episodes': a_episodes[episode]})
			show['seasons'] = seasons
			if 'tvshowid' in show_col1:
				del(show_col1['tvshowid'])
			result['shows'].append(show)

			i = i + 1
			y = ((i / x) * 8) + 2
			self.updateProgress(int(y), line2=utilities.getString(1483))

		self.updateProgress(10, line2=utilities.getString(1484))
		return result

	def countEpisodes(self, shows, watched=False, collection=True, all=False):
		count = 0
		p = 'seasons'
		if 'shows' in shows:
			shows = shows['shows']
		for show in shows:
			if all:
				for s in show[p]:
					count += len(show[p][s])
			else:
				if 'collected_at' in show and not show['collected_at'] == collection:
					continue
				for seasonKey in show[p]:
					for episodeKey in seasonKey['episodes']:
						if episodeKey['number']:
							count += 1
					
		return count
		
	def getShowAsString(self, show, short=False):
		p = []
		if 'seasons' in show:
			for season in show['seasons']:
				s = ""
				if short:
					s = ", ".join(["S%02dE%02d" % (season['number'], i['number']) for i in season['episodes']])
				else:
					episodes = ", ".join([str(i) for i in show['shows']['seasons'][season]])
					s = "Season: %d, Episodes: %s" % (season, episodes)
				p.append(s)
		else:
			p = ["All"]
		return "%s [tvdb: %s] - %s" % (show['title'], show['ids']['tvdb'], ", ".join(p))


	# def traktFormatShow(self, show):
	# 	data = {'title': show['title'], 'ids': {'tvdb': show['tvdb']}, 'year': show['year'], 'episodes': []}
	# 	if 'imdb' in show:
	# 		data['ids']['imdb'] = show['imdb']
	# 	if 'tvdb' in show:
	# 		data['ids']['tvdb'] = show['tvdb']			
	# 	for season in show['seasons']:
	# 		for episode in show['seasons'][season]:
	# 			data['episodes'].append({'season': season, 'episode': episode})
	# 	return data

	# this would return the data in format:
	#{1: {'tvdb': u'4954616', 'episodeid': 21736}, 
	# 2: {'tvdb': u'4954617', 'episodeid': 21737},
	# 3: {'tvdb': u'4942484', 'episodeid': 21738},
	# 4: {'tvdb': u'4973699', 'episodeid': 21739},
	# 5: {'tvdb': u'4982277', 'episodeid': 21740},
	# 6: {'tvdb': u'5017373', 'episodeid': 22303}}
	def getEpisodes(self, seasons, watched=False):
		data = {}
		for season in seasons:
			#Debug("getEpisodes season %s" % season)
			episodes = {}
			for episode in season['episodes']:
				#Debug("getEpisodes episode %s" % episode)
				if watched and episode['watched'] == 0:
						continue
				if (not watched) and 'collected' in episode and episode['collected'] == 0:
						continue
				episodes[episode['number']] = episode['ids']
			#Debug("getEpisodes episodes %s" % episodes)    
			#if len(episodes) > 0 :
			data[season['number']] = episodes
			#Debug("getEpisodes season %s episoded %s" % (season['number'],data[season['number']]))
		#Debug("getEpisodes %s" % data)   
		return data
	def compareShows(self, shows_col1, shows_col2, watched=False, restrict=False):
		shows = []
		p = 'watched' if watched else 'seasons'
		for show_col1 in shows_col1['shows']:
			show_col2 = utilities.findMediaObject(show_col1, shows_col2['shows'])

			if show_col2:
				Debug("show_col2 %s" % show_col2)
				season_diff = {}
				season1 = self.getEpisodes(show_col1['seasons'], watched)
				season2 = self.getEpisodes(show_col2['seasons'], watched)
				for season in season1:
					a = season1[season]
					if season in season2:
						b = season2[season]
						diff = list(set(a).difference(set(b)))
						if len(diff) > 0:
							if restrict:
								_seasons = self.getEpisodes(show_col2['seasons'], False)
								t = list(set(_seasons[season]).intersection(set(diff)))
								if len(t) > 0:
									eps = {}
									for ep in t:
										eps[ep] = _seasons[season][ep]
									season_diff[season] = eps
							else:
								eps = {}
								for ep in diff:
									eps[ep] = a[ep]
								season_diff[season] = eps
					else:
						if not restrict:
							if len(a) > 0:
								season_diff[season] = a
				if len(season_diff) > 0:
					show = {'title': show_col1['title'], 'ids' : {'tvdb': show_col1['ids']['tvdb']}, 'year': show_col1['year'], 'seasons': []}
					for seasonKey in season_diff:
						episodes = []
						for episodeKey in season_diff[seasonKey]:
							episodes.append({ 'number': episodeKey, 'ids': season_diff[seasonKey][episodeKey]})
						show['seasons'].append({ 'number': seasonKey, 'episodes': episodes })
					if 'imdb' in show_col1 and show_col1['imdb']:
						show['ids']['imdb'] = show_col1['imdb']
					if 'imdb' in show_col2 and show_col2['imdb']:
						show['ids']['imdb'] = show_col2['imdb']
					if 'tvshowid' in show_col1:
						show['tvshowid'] = show_col1['tvshowid']
					if 'tvshowid' in show_col2:
						show['tvshowid'] = show_col2['tvshowid']
					shows.append(show)
			else:
				if not restrict:
					if self.countEpisodes([show_col1], watched=watched) > 0:
						
						show = {'title': show_col1['title'], 'ids': {'tvdb': show_col1['ids']['tvdb']}, 'year': show_col1['year'], 'seasons': []}
						for seasonKey in show_col1['seasons']:
							episodes = []
							for episodeKey in seasonKey['episodes']:
								if 'ids' in episodeKey:
									ids = episodeKey['ids']
									if 'episodeid' in ids:
										del(ids['episodeid'])
								else:
									ids = {}
								episodes.append({ 'number': episodeKey['number'], 'ids': ids })
									
							show['seasons'].append({ 'number': seasonKey['number'], 'episodes': episodes })

						if 'tvshowid' in show_col1:
							del(show_col1['tvshowid'])
						#	show['tvshowid'] = show_col1['tvshowid']
						shows.append(show)
						Debug('show %s' % show)
		result = { 'shows': shows}
		return result

	def traktAddEpisodes(self, shows):
		if len(shows['shows']) == 0:
			self.updateProgress(46, line1=utilities.getString(1435), line2=utilities.getString(1490))
			Debug("[Episodes Sync] trakt.tv episode collection is up to date.")
			return
		Debug("[Episodes Sync] %i show(s) have episodes (%d) to be added to your trakt.tv collection." % (len(shows['shows']), self.countEpisodes(shows['shows'])))
		for show in shows['shows']:
			Debug("[Episodes Sync] Episodes added: %s" % self.getShowAsString(show, short=True))
		
		self.updateProgress(28, line1=utilities.getString(1435), line2="%i %s" % (len(shows['shows']), utilities.getString(1436)), line3=" ")

		Debug("[trakt][traktAddEpisodes] Shows to add %s" % shows)
		result = self.traktapi.addToCollection(shows)
		Debug("[trakt][traktAddEpisodes] Result %s" % result)
        
		self.updateProgress(46, line1=utilities.getString(1435), line2=utilities.getString(1491) % self.countEpisodes(shows['shows']))

	def traktRemoveEpisodes(self, shows):
		if len(shows['shows']) == 0:
			self.updateProgress(98, line1=utilities.getString(1445), line2=utilities.getString(1496))
			Debug('[Episodes Sync] trakt.tv episode collection is clean')
			return

		Debug("[Episodes Sync] %i show(s) will have episodes removed from trakt.tv collection." % len(shows['shows']))
		for show in shows['shows']:
			Debug("[Episodes Sync] Episodes removed: %s" % self.getShowAsString(show, short=True))

		self.updateProgress(82, line1=utilities.getString(1445), line2=utilities.getString(1497) % self.countEpisodes(shows), line3=" ")

		Debug("[trakt][traktRemoveEpisodes] Shows to remove %s" % shows)
		result = self.traktapi.removeFromCollection(shows)
		Debug("[trakt][traktRemoveEpisodes] Result %s" % result)
        
		self.updateProgress(98, line2=utilities.getString(1498) % self.countEpisodes(shows['shows']), line3=" ")

	def traktUpdateEpisodes(self, shows):
		if len(shows['shows']) == 0:
			self.updateProgress(64, line1=utilities.getString(1438), line2=utilities.getString(1492))
			Debug("[Episodes Sync] trakt.tv episode playcounts are up to date.")
			return

		Debug("[Episodes Sync] %i show(s) are missing playcounts on trakt.tv" % len(shows['shows']))
		for show in shows['shows']:
			Debug("[Episodes Sync] Episodes updated: %s" % self.getShowAsString(show, short=True))

		self.updateProgress(46, line1=utilities.getString(1438), line2="%i %s" % (len(shows['shows']), utilities.getString(1439)), line3=" ")

		i = 0
		x = float(len(shows['shows']))
		for show in shows['shows']:
			if self.isCanceled():
				return

			epCount = self.countEpisodes([show])
			title = show['title'].encode('utf-8', 'ignore')

			i = i + 1
			y = ((i / x) * 18) + 46
			self.updateProgress(70, line2=title, line3="%i %s" % (epCount, utilities.getString(1440)))

			s = { 'shows': [show]}
			if self.simulate:
				Debug("[Episodes Sync] %s" % str(s))
			else:
				Debug("[trakt][traktUpdateEpisodes] Shows to update %s" % s)
				result = self.traktapi.updateSeenEpisode(s)
				Debug("[trakt][traktUpdateEpisodes] Result %s" % result)

		self.updateProgress(64, line2="%i %s" % (len(shows['shows']), utilities.getString(1439)))

	def xbmcUpdateEpisodes(self, shows):
		if len(shows['shows']) == 0:
			self.updateProgress(82, line1=utilities.getString(1441), line2=utilities.getString(1493))
			Debug("[Episodes Sync] Kodi episode playcounts are up to date.")
			return

		Debug("[Episodes Sync] %i show(s) shows are missing playcounts on Kodi" % len(shows['shows']))
		for s in ["%s" % self.getShowAsString(s, short=True) for s in shows['shows']]:
			Debug("[Episodes Sync] Episodes updated: %s" % s)

		self.updateProgress(64, line1=utilities.getString(1441), line2="%i %s" % (len(shows['shows']), utilities.getString(1439)), line3=" ")

		episodes = []
		for show in shows['shows']:
			for season in show['seasons']:
				for episode in season['episodes']:
					episodes.append({'episodeid': episode['ids']['episodeid'], 'playcount': 1})

		#split episode list into chunks of 50
		chunked_episodes = utilities.chunks([{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": episodes[i], "id": i} for i in range(len(episodes))], 50)
		i = 0
		x = float(len(chunked_episodes))
		for chunk in chunked_episodes:
			if self.isCanceled():
				return
			if self.simulate:
				Debug("[Episodes Sync] %s" % str(chunk))
			else:
				Debug("[Episodes Sync] chunk %s" % str(chunk))
				result = utilities.xbmcJsonRequest(chunk)
				Debug("[Episodes Sync] result %s" % str(result))

			i = i + 1
			y = ((i / x) * 18) + 64
			self.updateProgress(int(y), line2=utilities.getString(1494))

		self.updateProgress(82, line2=utilities.getString(1495) % len(episodes))

	def syncEpisodes(self):
		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1406)), utilities.getString(1420)) #Sync started
		if self.show_progress and not self.run_silent:
			progress.create("%s %s" % (utilities.getString(1400), utilities.getString(1406)), line1=" ", line2=" ", line3=" ")

		xbmcShows = self.xbmcLoadShows()
		Debug("xbmcShows %s" % xbmcShows)
		if not isinstance(xbmcShows, list) and not xbmcShows:
			Debug("[Episodes Sync] Kodi show list is empty, aborting tv show Sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		traktShows = self.traktLoadShows()
		Debug("traktShows %s" % traktShows)
		if not isinstance(traktShows['shows'], list):
			Debug("[Episodes Sync] Error getting trakt.tv show list, aborting tv show sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		if utilities.getSettingAsBool('add_episodes_to_trakt') and not self.isCanceled():
			traktShowsAdd = self.compareShows(xbmcShows, traktShows)
			Debug("traktShowsAdd %s" % traktShowsAdd)
			self.traktAddEpisodes(traktShowsAdd)

		
		if utilities.getSettingAsBool('trakt_episode_playcount') and not self.isCanceled():
			traktShowsUpdate = self.compareShows(xbmcShows, traktShows, watched=True)
			self.traktUpdateEpisodes(traktShowsUpdate)

		if utilities.getSettingAsBool('xbmc_episode_playcount') and not self.isCanceled():
			xbmcShowsUpadate = self.compareShows(traktShows, xbmcShows, watched=True, restrict=True)
			self.xbmcUpdateEpisodes(xbmcShowsUpadate)

		if utilities.getSettingAsBool('clean_trakt_episodes') and not self.isCanceled():
			traktShowsRemove = self.compareShows(traktShows, xbmcShows)
			self.traktRemoveEpisodes(traktShowsRemove)

		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1406)), utilities.getString(1421)) #Sync complete

		if not self.isCanceled() and self.show_progress and not self.run_silent:
			self.updateProgress(100, line1=" ", line2=utilities.getString(1442), line3=" ")
			progress.close()

		#Debug("[Episodes Sync] Shows on trakt.tv (%d), shows in Kodi (%d)." % (len(utilities.findAllInList(traktShows['shows'], 'collected_at', True)), len(xbmcShows['shows'])))
		Debug("[Episodes Sync] Shows on trakt.tv (%d), shows in Kodi (%d)." % (len(traktShows['shows']), len(xbmcShows['shows'])))

		Debug("[Episodes Sync] Episodes on trakt.tv (%d), episodes in Kodi (%d)." % (self.countEpisodes(traktShows), self.countEpisodes(xbmcShows)))
		Debug("[Episodes Sync] Complete.")

	''' begin code for movie sync '''
	def traktLoadMovies(self):
		self.updateProgress(5, line2=utilities.getString(1462))

		Debug("[Movies Sync] Getting movie collection from trakt.tv")
		traktMovies = {}
		traktMovies = self.traktapi.getMoviesLibrary(traktMovies)
		traktMovies = self.traktapi.getMoviesWatched(traktMovies)
		traktMovies = traktMovies.items()
		if not isinstance(traktMovies, list):
			Debug("[Movies Sync] Invalid trakt.tv movie list, possible error getting data from trakt, aborting trakt.tv collection update.")
			return False

		self.updateProgress(20, line2=utilities.getString(1466))
		movies = []
		for key, movie in traktMovies:
			movie = vars(movie)
			
			movies.append(movie)



		return movies

	def xbmcLoadMovies(self):
		self.updateProgress(1, line2=utilities.getString(1460))

		Debug("[Movies Sync] Getting movie data from Kodi")
		data = utilities.xbmcJsonRequest({'jsonrpc': '2.0', 'id': 0, 'method': 'VideoLibrary.GetMovies', 'params': {'properties': ['title', 'imdbnumber', 'year', 'playcount', 'lastplayed', 'file']}})
		if not data:
			Debug("[Movies Sync] Kodi JSON request was empty.")
			return
		
		if not 'movies' in data:
			Debug('[Movies Sync] Key "movies" not found')
			return

		movies = data['movies']
		Debug("[Movies Sync] Kodi JSON Result: '%s'" % str(movies))

		i = 0
		x = float(len(movies))
		
		xbmc_movies = []

		# reformat movie array
		for movie in movies:
			if self.checkExclusion(movie['file']):
				continue
			if movie['lastplayed']:
				movie['last_played'] = utilities.sqlDateToUnixDate(movie['lastplayed'])
			movie['plays'] = movie.pop('playcount')
			movie['collected_at'] = datetime.datetime.now().isoformat()
			movie['ids'] = {}
			id = movie['imdbnumber']
			if id.startswith("tt"):
				movie['ids']['imdb'] = ""
				movie['ids']['imdb'] = id
			if id.isdigit():
				movie['ids']['tmdb'] = ""
				movie['ids']['tmdb'] = id
			del(movie['imdbnumber'])
			del(movie['lastplayed'])
			del(movie['label'])
			del(movie['file'])

			xbmc_movies.append(movie)

			i = i + 1
			y = ((i / x) * 4) + 1
			self.updateProgress(int(y))
			
		self.updateProgress(5, line2=utilities.getString(1461))

		return xbmc_movies

	def compareMovies(self, movies_col1, movies_col2, watched=False):
		movies = []
		for movie_col1 in movies_col1:
			movie_col2 = utilities.findMediaObject(movie_col1, movies_col2)

			if movie_col2:
				if watched:
					if (movie_col2['plays'] == 0) and (movie_col1['plays'] > movie_col2['plays']):
						if 'movieid' not in movie_col1:
							movie_col1['movieid'] = movie_col2['movieid']
						movies.append(movie_col1)
				else:
					if 'collected_at' in movie_col2 and not movie_col2['collected_at']:
						movies.append(movie_col1)
		return movies

	def traktAddMovies(self, movies):
		if len(movies) == 0:
			self.updateProgress(40, line2=utilities.getString(1467))
			Debug("[Movies Sync] trakt.tv movie collection is up to date.")
			return

		titles = ", ".join(["%s (%s)" % (m['title'], m['ids']['imdb']) for m in movies])
		Debug("[Movies Sync] %i movie(s) will be added to trakt.tv collection." % len(movies))

		self.updateProgress(20, line2="%i %s" % (len(movies), utilities.getString(1426)))

		moviesToAdd = {}
		moviesToAdd['movies'] = movies

		self.traktapi.addToCollection(moviesToAdd)

		self.updateProgress(40, line2=utilities.getString(1468) % len(movies))

	def kodiUpdateMovies(self, movies):
		if len(movies) == 0:
			self.updateProgress(80, line2=utilities.getString(1471))
			Debug("[Movies Sync] XBMC movie playcount is up to date.")
			return
		
		Debug("[Movies Sync] %i movie(s) playcount will be updated in XBMC" % len(movies))

		self.updateProgress(60, line2="%i %s" % (len(movies), utilities.getString(1430)))

		#split movie list into chunks of 50
		chunked_movies = utilities.chunks([{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": movies[i]['movieid'], "playcount": movies[i]['plays']}, "id": i} for i in range(len(movies))], 50)
		i = 0
		x = float(len(chunked_movies))
		for chunk in chunked_movies:
			if self.isCanceled():
				return
			utilities.xbmcJsonRequest(chunk)

			i = i + 1
			y = ((i / x) * 20) + 60
			self.updateProgress(int(y), line2=utilities.getString(1472))

		self.updateProgress(80, line2=utilities.getString(1473) % len(movies))

	def traktRemoveMovies(self, movies):
		if len(movies) == 0:
			self.updateProgress(98, line2=utilities.getString(1474))
			Debug("[Movies Sync] trakt.tv movie collection is clean, no movies to remove.")
			return
		
		titles = ", ".join(["%s (%s)" % (m['title'], m['ids']['imdb']) for m in movies])
		Debug("[Movies Sync] %i movie(s) will be removed from trakt.tv collection." % len(movies))
		Debug("[Movies Sync] Movies removed: %s" % titles)

		self.updateProgress(80, line2="%i %s" % (len(movies), utilities.getString(1444)))
		
		moviesToRemove = {}
		moviesToRemove['movies'] = movies

		self.traktapi.removeFromCollection(moviesToRemove)

		self.updateProgress(98, line2=utilities.getString(1475) % len(movies))

	def syncMovies(self):
		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1402)), utilities.getString(1420)) #Sync started
		if self.show_progress and not self.run_silent:
			progress.create("%s %s" % (utilities.getString(1400), utilities.getString(1402)), line1=" ", line2=" ", line3=" ")

		kodiMovies = self.xbmcLoadMovies()
		if not isinstance(kodiMovies, list) and not kodiMovies:
			Debug("[Movies Sync] Kodi movie list is empty, aborting movie Sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		traktMovies = self.traktLoadMovies()
		if not isinstance(traktMovies, list):
			Debug("[Movies Sync] Error getting trakt.tv movie list, aborting movie Sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		if utilities.getSettingAsBool('add_movies_to_trakt') and not self.isCanceled():
			traktMoviesToAdd = self.compareMovies(kodiMovies, traktMovies)
			Debug("[Movies Sync] Compared movies, found %s to add." % len(traktMoviesToAdd))
			self.traktAddMovies(traktMoviesToAdd)

		if utilities.getSettingAsBool('kodi_movie_playcount') and not self.isCanceled():
			kodiMoviesToUpdate = self.compareMovies(traktMovies, kodiMovies, watched=True)
			self.kodiUpdateMovies(kodiMoviesToUpdate)

		if utilities.getSettingAsBool('clean_trakt_movies') and not self.isCanceled():
			Debug("[Movies Sync] Starting to remove.")
			traktMoviesToRemove = self.compareMovies(traktMovies, kodiMovies)
			Debug("[Movies Sync] Compared movies, found %s to remove." % len(traktMoviesToRemove))
			self.traktRemoveMovies(traktMoviesToRemove)

		if not self.isCanceled() and self.show_progress and not self.run_silent:
			self.updateProgress(100, line1=utilities.getString(1431), line2=" ", line3=" ")
			progress.close()

		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1402)), utilities.getString(1421)) #Sync complete
		
		Debug("[Movies Sync] Movies on trakt.tv (%d), movies in Kodi (%d)." % (len(traktMovies), len(kodiMovies)))
		Debug("[Movies Sync] Complete.")

	def syncCheck(self, media_type):
		if media_type == 'movies':
			return utilities.getSettingAsBool('add_movies_to_trakt') or utilities.getSettingAsBool('trakt_movie_playcount') or utilities.getSettingAsBool('xbmc_movie_playcount') or utilities.getSettingAsBool('clean_trakt_movies')
		else:
			return utilities.getSettingAsBool('add_episodes_to_trakt') or utilities.getSettingAsBool('trakt_episode_playcount') or utilities.getSettingAsBool('xbmc_episode_playcount') or utilities.getSettingAsBool('clean_trakt_episodes')

		return False

	def sync(self):
		Debug("[Sync] Starting synchronization with trakt.tv")

		if self.syncCheck('movies'):
			if self.library in ["all", "movies"]:
				self.syncMovies()
			else:
				Debug("[Sync] Movie sync is being skipped for this manual sync.")
		else:
			Debug("[Sync] Movie sync is disabled, skipping.")

		if self.syncCheck('episodes'):
			if self.library in ["all", "episodes"]:
				self.syncEpisodes()
			else:
				Debug("[Sync] Episode sync is being skipped for this manual sync.")
		else:
			Debug("[Sync] Episode sync is disabled, skipping.")

		Debug("[Sync] Finished synchronization with trakt.tv")
	
