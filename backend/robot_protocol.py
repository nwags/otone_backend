import json, os

from deck_module import DeckModule
from file_io import FileIO


debug = True

class RobotProtocol:
	"""Port of createJobFile.js into python, start of move to a new framework.
		1st move createJobFile into python
		2nd piece by piece replace it with pieces from new framework"""

	def __init__(self, protocol, containers, pipette_calibrations):
		# 0. Added pipette calibrations run through for highestSpot
		self.highestSpot = 500

		#FileIO.log('pipette_calibrations... ',type(pipette_calibrations))
		#FileIO.log(pipette_calibrations)
		self.pipette_calibrations = pipette_calibrations
		for axis_name, axis_values in self.pipette_calibrations.items():
			if 'theContainers' in list(axis_values):
				for container_name, container_value in axis_values['theContainers'].items():
					if 'z' in list(container_value):
						if container_value['z'] is not None:
							if float(container_value['z']) < self.highestSpot:
								self.highestSpot = float(container_value['z'])
		
		if self.highestSpot > 200 or self.highestSpot < 0:
			self.highestSpot = 0


		# 1. create representation of wells (coordinates & current volume)
		self.protocol = dict()
		self.labware_from_db = dict()
		if isinstance(protocol, dict):
			self.protocol = protocol
		if isinstance(containers, dict):
			self.labware_from_db = containers['containers']

		self._deck = dict()

		#FileIO.log('protocol... ',type(protocol))
		#FileIO.log(protocol)

		#FileIO.log('containers... ',type(containers))
		#FileIO.log(list(containers['containers']))
		#FileIO.log('self.labware_from_db... ',type(self.labware_from_db))
		#FileIO.log(list(self.labware_from_db))



	def process(self):
		for variableName, variableValue in self.protocol['deck'].items():
			_container = dict()
			#FileIO.log('variableValue... ',type(variableValue))
			#FileIO.log(variableValue)
			labwareName = variableValue['labware']
			_container['labware'] = labwareName
		
			if len(list(self.labware_from_db))>0 and labwareName in list(self.labware_from_db):
				_container['locations'] = self.labware_from_db[labwareName]['locations']
		
				if 'locations' in list(_container):
					for locationName, locationValue in _container['locations'].items():
						#currentLocation = locationValue
						if 'total-liquid-volume' in list(locationValue):#currentLocation):
							self.createLiquidLocation(locationValue)#currentLocation)
			else:
				FileIO.log('"',labwareName,'" not found in labware definitions')

			self._deck[variableName] = _container

		#2. Now add the starting ingredients to those created locations (wells)

		for ingredientName, ingredientValue in self.protocol['ingredients'].items():
			ingredientPartsList = ingredientValue
			#FileIO.log('calling map & ingredientPartList/Update...')
			map(lambda self, ingredientPart: self.ingredientPartUpdate(ingredientPart),ingredientPartsList)

		
		#3. Give the pipettes access to the deck, so they can do .pickupTip() and .dropTip()

		self._pipettes = dict()

		for toolName, toolValue in self.protocol['head'].items():
			self._pipettes[toolName] = toolValue
			self._pipettes[toolName]['tip-rack-objs'] = dict()
			self._pipettes[toolName]['trash-container-objs'] = dict()
			self._pipettes[toolName]['current-plunger'] = 0
			
			self._pipettes[toolName]['distribute-percentage'] = 0
			#FileIO.log('toolName: ',toolName,' toolValue: ',toolValue)
			if 'down-plunger-speed' in list(toolValue):
				if isinstance(toolValue['down-plunger-speed'],(int,float,complex)):
					self._pipettes[toolName]['down-plunger-speed'] = toolValue['down-plunger-speed']
			else:
				self._pipettes[toolName]['down-plunger-speed'] = 300
			if 'up-plunger-speed' in list(toolValue):
				if isinstance(toolValue['up-plunger-speed'],(int,float,complex)):
					self._pipettes[toolName]['up-plunger-speed'] = toolValue['up-plunger-speed']
			else:
				self._pipettes[toolName]['down-plunger-speed'] = 600
			if 'distribute-percentage' in list(toolValue):
				if toolValue['distribute-percentage'] < 0:
					self._pipettes[toolName]['distribute-percentage'] = 0
				if toolValue['distribute-percentage'] > 1:
					self._pipettes[toolName]['distribute-percentage'] = 1
			if 'points' in list(toolValue):
				self._pipettes[toolName]['points'].sort(key=lambda a: a['f1'])

			_trashcontainerName = ""

			if isinstance(self._pipettes[toolName]['trash-container'], list):
				_trashcontainerName = self._pipettes[toolName]['trash-container'][0].strip()
			else:
				_trashcontainerName = self._pipettes[toolName]['trash-container']['container'].strip()
			if len(_trashcontainerName)>0 and _trashcontainerName in list(self._deck):
				trashLabware = self._deck[_trashcontainerName]['labware']
				if trashLabware is not None:
					self._pipettes[toolName]['trash-container-objs'][_trashcontainerName] = dict()
					self._pipettes[toolName]['trash-container-objs'][_trashcontainerName]['locations'] = self.labware_from_db[trashLabware]['locations']
			else:
				FileIO.log('"',_trashcontainerName,'" not found in deck')

			_tr_list = list()
			_tr_list = self._pipettes[toolName]['tip-racks']
			_tr_objs = dict()
			if len(_tr_list) > 0:
				for _rack in _tr_list:
					containerName = ""
					if isinstance(_rack,str):
						containerName = _rack.strip()
					else:
						containerName = _rack['container'].strip()
					_tr_objs[containerName] = dict()
					_tr_objs[containerName]['container'] = containerName
					_tr_objs[containerName]['clean-tips'] = list()
					_tr_objs[containerName]['dirty-tips'] = list()

					labwareName = self._deck[containerName]['labware'].strip()

					if labwareName in self.labware_from_db:
						_locations = self.labware_from_db[labwareName]['locations']
						#FileIO.log(' *** locations ***')
						#FileIO.log(_locations)
						l_locations = list(_locations)
						#FileIO.log(l_locations)
						l_locations.sort(key=self.sortIndex)
						#FileIO.log('after sort...')
						#FileIO.log(l_locations)
						#locs = list(_locations).sort(key=self.sortIndex)
						#FileIO.log('locs')
						#FileIO.log(locs)
						for locName in l_locations: #locs:#list(_locations):
							_tr_objs[containerName]['clean-tips'].append(_locations[locName])
					else:
						FileIO.log('"',labwareName,'" not found in labware definitions')
				self._pipettes[toolName]['tip-rack-objs'] = _tr_objs
				self._pipettes[toolName]['pickupTip'] = lambda pipette: self._pickupTip(pipette)
				self._pipettes[toolName]['dropTip'] = lambda pipette: self._dropTip(pipette)

		#4. Make array of instructions, to hold commands and their individual move locations

		self.createdInstructions = list()

		self._instructions = self.protocol['instructions']

		for toolname in self._pipettes:
			ci = dict(
				{
					'tool' : self._pipettes[toolname]['tool'],
					'groups' : [
						{
							'command':'pipette',
							'axis':self._pipettes[toolname]['axis'],
							'locations': [
								{
									'plunger':'blowout'
								},
								{
									'plunger':'resting'
								},
								{
									'plunger':'blowout'
								},
								{
									'plunger':'resting'
								}
							]
						}
					]
				}
				)
				
			self.createdInstructions.append(ci)

			for instruction in self._instructions:
				currentPipette = self._pipettes[instruction['tool']]
				#FileIO.log('currentPipette... ',type(currentPipette))
				#FileIO.log(currentPipette)
				if currentPipette is not None:
					newInstruction = dict()
					newInstruction['tool'] = currentPipette['tool']
					newInstruction['groups'] = list()

					for g in instruction['groups']:
						newGroup = None
						if 'transfer' in list(g):
							newGroup = self.transfer(self._deck, currentPipette, g['transfer'])
							#FileIO.log('newGroup... ',type(newGroup))
							#FileIO.log(newGroup)
						elif 'distribute' in list(g):
							newGroup = self.distribute(self._deck, currentPipette, g['distribute'])
							#FileIO.log('newGroup... ',type(newGroup))
							#FileIO.log(newGroup)
						elif 'consolidate' in list(g):
							newGroup = self.consolidate(self._deck, currentPipette, g['consolidate'])
							#FileIO.log('newGroup... ',type(newGroup))
							#FileIO.log(newGroup)
						elif 'mix' in list(g):
							newGroup = self.mix(self._deck, pipette, g['mix'])
							
						#FileIO.log('newGroup... ',type(newGroup))
						#FileIO.log(newGroup)
						if newGroup is not None:
							newInstruction['groups'].append(newGroup)
							#FileIO.log('newInstruction[groups]... ',type(newInstruction['groups']))
							#FileIO.log(newInstruction['groups'])
				self.createdInstructions.append(newInstruction)
				#FileIO.log('self.createdInstructions... ',type(self.createdInstructions))
				#FileIO.log(self.createdInstructions)

		return self.createdInstructions

	def sortIndex(self, index):
		#FileIO.log('sortIndex called')
		integer = ord(index[:1])*pow(10,len(index[1:]))
		decimal = int(index[1:])#/pow(10,len(index[1:]))
		return integer+decimal


	def createLiquidLocation(self, location):
		#FileIO.log('createLiquidLocation called')
		location['current-liquid-volume'] = 0
		location['current-liquid-offset'] = 0
		location['updateVolume'] = lambda location, ingredientVolume: self.updateVolume(location, ingredientVolume)


	def updateVolume(self, location, ingredientVolume):
		"""turned into lambda for location dict"""
		#FileIO.log('updateVolume called')
		location['current-liquid-volume'] += ingredientVolume
		heightRatio = location['current-liquid-volume'] / location['total-liquid-volume']
		if isinstance(heightRatio,(int,float,complex)):
			location['current-liquid-volume'] = location['depth'] - (location['depth'] * heightRatio)


	def ingredientPartUpdate(self, ingredientPart):
		#FileIO.log('ingredientPartUpdate called')
		if 'container' in list(ingredientPart) and ingredientPart['container'] in list(self._deck):
			allLocations = self._deck[ingredientPart.container]['locations']
			if 'location' in list(ingredientPart) and ingredientPart.location in list(allLocations):
				currentLocation = allLocations[ingredientPart['location']]
				ingredientVolume = ingredientPart['volume']

				if isinstance(ingredientVolume, (int, float, complex)) and 'updateVolume' in list(currentLocation):
					currentLocation['updateVolume'](currentLocation, ingredientVolume)


	def _pickupTip(self, pipette):
		myRacks = pipette['tip-rack-objs']
		pipette['justPickedUp'] = True

		newTipLocation = None
		newTipContainerName = None

		for rackName, rackValue in myRacks.items():
			if len(rackValue['clean-tips'])>0:
				howManyTips = 8 if (pipette['multi-channel'] == True) else 1
				if not isinstance(howManyTips,int):
					howManyTips = 1
				newTipLocation = rackValue['clean-tips'][0:1][0] #.splice(0,1)[0]
				newTipContainerName = ""
				newTipContainerName = rackValue['container']
				rackValue['dirty-tips'].append(newTipLocation)
				for n in range(howManyTips-1):
					tempTip = rackValue['clean-tips'][0:1][0] #.splice(0,1)[0]
					if tempTip is not None:
						rackValue['dirty-tips'].append(tempTip)
				break;

		if newTipLocation is not None:
			for rackName, rackValue in myRacks.items():
				rackValue['clean-tips'] = rackValue['dirty-tips']
				rackValue['dirty-tips'] = []

			if len(list(myRacks)) > 0:
				#FileIO.log('myRacks... ',type(myRacks))
				#FileIO.log(myRacks)
				#FileIO.log('myRacks.keys()...',type(myRacks.keys()))
				#FileIO.log(myRacks.keys())
				#FileIO.log('myRacks clean-tips')
				#FileIO.log('myRacks[list(myRacks)[0]]... ',type(myRacks[list(myRacks)[0]]))
				#FileIO.log(myRacks[list(myRacks)[0]])
				newTipLocation = myRacks[list(myRacks)[0]]['clean-tips'][0:1][0] #.splice(0,1)[0]
				newTipContainerName = myRacks[list(myRacks)[0]]['container']
				myRacks[list(myRacks)[0]]['dirty-tips'].append(newTipLocation)

		moveList = list()

		movie = dict({'z':0})
		moveList.append(movie)
		
		pipette['current-plunger'] = 0
		
		movie = dict({'plunger':'resting'})
		moveList.append(movie)

		movie = dict({'x':newTipLocation['x'],'y':newTipLocation['y'],'container':newTipContainerName})
		moveList.append(movie)

		for i in range(3):
			movie = dict({'z':newTipLocation['z']-pipette['tip-plunge'],'container':newTipContainerName})
			moveList.append(movie)

			movie = dict({'z':newTipLocation['z']+1,'container':newTipContainerName})
			moveList.append(movie)

		return moveList


	def _dropTip(self, pipette):
		moveList = list()
		trashContainerName = ""

		if isinstance(pipette['trash-container'], list):
			trashContainerName = pipette['trash-container'][0]
		else:
			trashContainerName = pipette['trash-container']['container']

		trashLocation = None
		for o,v in pipette['trash-container-objs'][trashContainerName]['locations'].items():
			trashLocation = v

		movie = dict({'z':0})
		moveList.append(movie)

		pipette['current-plunger'] = 0

		movie = dict({'plunger':'resting'})
		moveList.append(movie)

		movie = dict({'x':trashLocation['x'],'y':trashLocation['y'],'container':trashContainerName})
		moveList.append(movie)

		movie = dict({'z':trashLocation['z'],'container':trashContainerName})
		moveList.append(movie)

		movie = dict({'plunger':'droptip'})
		moveList.append(movie)

		return moveList





	def transfer(self, theDeck, theTool, transferList):
		#FileIO.log('transfer called')
		createdGroup = dict({
			'command':'pipette',
			'axis':theTool['axis'],
			'locations':list()
			})
		pickupList = theTool['pickupTip'](theTool)
		createdGroup['locations'].extend(pickupList)

		for i in transferList:
			thisTransferParams = i
			fromParams = thisTransferParams['from']
			toParams = thisTransferParams['to']
			volume = thisTransferParams['volume']

			fromParams['volume'] = volume * -1
			toParams['volume'] = volume
			#FileIO.log('thisTransferParams... ',type(thisTransferParams))
			#FileIO.log(thisTransferParams)

			if 'extra-pull' in list(thisTransferParams):
				fromParams['extra-pull'] = thisTransferParams['extra-pull']

			fromList = self.makePipettingMotion(theDeck, theTool, fromParams, True)
			createdGroup['locations'].extend(fromList) #replaces _addMovements(fromArray)

			toList = self.makePipettingMotion(theDeck, theTool, toParams, False)
			createdGroup['locations'].extend(toList)

		dropList = theTool['dropTip'](theTool)
		createdGroup['locations'].extend(dropList)

		return createdGroup


	def distribute(self, theDeck, theTool, distributeGroup):
		createdGroup = dict({
				'command':'pipette',
				'axis':theTool['axis'],
				'locations':list()
			})
		pickupList = theTool['pickupTip'](theTool)
		createdGroup['locations'].extend(pickupList)

		toParamsList = distributeGroup['to']
		totalPercentage = 0
		for i in list(toParamsList):
			totalPercentage += getPercentage(i['volume'],theTool)
		totalVolume = theTool['volume'] * totalPercentage
		totalVolume += totalVolume * theTool['distribute-percentage']
		if totalVolume > theTool['volume']:
			totalVolume = float(theTool['volume'])

		fromParams = distributeGroup['list']
		fromParams['volume'] = totalVolume * -1

		if 'extra-pull' in list(distributeGroup):
			fromParams['extra-pull'] = distributeGroup['extra-pull']
		
		tempFromList = self.makePipettingMotion(theDeck, theTool, fromParams, False)
		createdGroup['locations'].extend(tempFromList)

		dropList = theTool['dropTip'](theTool)
		createdGroup['locations'].extend(dropList)

		return createdGroup


	def consolidate(self, theDeck, theTool, consolidateGroup):
		createdGroup = dict({
				'command':'pipette',
				'axis':theTool['axis'],
				'locations':list()
			})
		pickupList = theTool['pickupTip'](theTool)
		createdGroup['locations'].extend(pickupList)

		fromParamsList = consolidatedGroup['from']
		totalPercentage = 0

		for i in list(fromParamsList):
			fromParams = i
			totalPercentage += self.getPercentage(fromParams['volume'], theTool)
			fromParams['volume'] *= -1
			
			if 'extra-pull' in list(consolidateGroup):
				fromParams['extra-pull'] = consolidateGroup['extra-pull']

			tempFromList = self.makePipettingMotion(theDeck, theTool, fromParams, i==0)
			createdGroup['locations'].extend(tempFromList)

		totalVolume = totalPercentage * theTool['volume']

		toParams = consolidatedGroup['to']
		toParams['volume'] = totalVolume

		tempToList = self.makePipettingMotion(theDeck, theTool, toParams, False)
		createdGroup['locations'].extend(tempToList)

		return createdGroup


	def mix(self, theDeck, theTool, mixListOfDicts):
		createdGroup = dict({
				'command':'pipette',
				'axis':theTool['axis'],
				'locations':list()
			})

		pickupList = theTool['pickupTip'](theTool)
		createdGroup['locations'].extend(pickupList)

		for i in list(mixListOfDicts):
			thisParam = i
			thisParam['volume'] *= -1
			mixMoveCommands = self.makePipettingMotion(theDeck, theTool, thisParam, True)
			createdGroup['locations'].extend(mixMoveCommands)

		dropList = theTool['dropTip'](theTool)
		createdGroup['locations'].extend(dropList)

		return createdGroup


	def makePipettingMotion(self, theDeck, theTool, thisParams, shouldDropPlunger):
		moveList = list()
		containerName = thisParams['container']
		FileIO.log('containerName: ',containerName)
		FileIO.log('thisParams["location"]: ',thisParams['location'])
		FileIO.log(containerName,' locations:')
		FileIO.log(list(theDeck[containerName]['locations']))
		if containerName in list(theDeck) and 'locations' in list(theDeck[containerName]):
			locationPos = theDeck[containerName]['locations'][thisParams['location']]
			#FileIO.log('locationPos... ',type(locationPos))
			#FileIO.log(locationPos)
			if 'updateVolume' in list(locationPos):
				locationPos['updateVolume'](locationPos, float(thisParams['volume']))
			specifiedOffset = 0
			if 'tip-offset' in list(thisParams):
				specifiedOffset = float(thisParams['tip-offset'])
			
			bottomLimit = (locationPos['depth'] - 0.2) * -1
			arriveDepth = bottomLimit + specifiedOffset

			if 'liquid-tracking' in list(thisParams):
				if thisParams['liquid-tracking'] == True:
					arriveDepth = specifiedOffset-locationPos['current-liquid-offset']

			#if arriveDepth < bottomLimit:
			#	arriveDepth = bottomLimit
			#FileIO.log('theTool... ',type(theTool))
			#FileIO.log(theTool)
			moveList.append(dict({'speed':theTool['down-plunger-speed']}))

			rainbowHeight = self.highestSpot - 5

			if theTool['justPickedUp'] == True:
				rainbowHeight = 0
				theTool['justPickedUp'] = False

			moveList.append(dict({'z':rainbowHeight}))

			if shouldDropPlunger == True:
				theTool['current-plunger'] = 0
				moveList.append(dict({'plunger':'resting'}))

			moveList.append(dict({
						'x':locationPos['x'],
						'y':locationPos['y'],
						'container':containerName
					}))
			moveList.append(dict({
						'z':1,
						'container':containerName
					}))

			if shouldDropPlunger == True:
				theTool['current-plunger'] = 0.1
				moveList.append(dict({
						'plunger':theTool['current-plunger']
					}))
				theTool['current-plunger'] = 0.95
				moveList.append(dict({
						'plunger':theTool['current-plunger']
					}))
			
			moveList.append(dict({
						'z':arriveDepth,
						'container':containerName
					}))
			if shouldDropPlunger == True:
				theTool['current-plunger'] = 1
				moveList.append(dict({
						'plunger':theTool['current-plunger']
					}))
			if 'delay' in list(thisParams):
				if isinstance(thisParams['delay'],(int,float,complex)):
					moveList.append(dict({
							'delay':thisParams['delay']
						}))
			
			plungerPercentage = self.getPercentage(thisParams['volume'], theTool)
			extraPercentage = 0

			if 'repetitions' in list(thisParams):
				if 'updateVolume' in list(locationPos):
					locationPos['updateVolume'](locationPos, float(thisParams['volume'] * -1))

				for i in range(int(thisParams['repititions'])):
					moveList.append(dict({
							'speed':theTool['up-plunger-speed']
						}))
					theTool['current-plunger']+=plungerPercentage
					moveList.append(dict({
							'plunger':theTool['current-plunger']
						}))
					moveList.append(dict({
							'speed':theTool['down-plunger-speed']
						}))
					theTool['current-plunger']-=plungerPercentage
					moveList.append(dict({
							'plunger':theTool['current-plunger']
						}))
			else:
				if shouldDropPlunger==True and 'extra-pull-volume' in list(theTool) and 'extra-pull' in list(thisParams):
					extraPercentage = (float(theTool['extra-pull-volume'])/theTool['volume'])

				moveList.append(dict({
						'speed':theTool['up-plunger-speed']
					}))

				theTool['current-plunger']+=(plungerPercentage - extraPercentage)
				if theTool['current-plunger']<0:
					theTool['current-plunger'] = 0
				moveList.append(dict({
						'plunger':theTool['current-plunger']
					}))
				if extraPercentage!=0:
					delayTime = 0.200
					if 'extra-pull-delay' in list(theTool):
						if isinstance(theTool['extra-pull-delay'],(int,float,complex)):
							delayTime = abs(theTool['extra-pull-delay'])
					moveList.append(dict({'delay':delaytime}))

					moveList.append(dict({'speed':theTool['down-plunger-speed']}))

					theTool['current-plunger'] += extraPercentage
					moveList.append(dict({'plunger':theTool['current-plunger']}))

				if 'delay' in list(theTool):
					if isinstance(theTool['delay'],(int,float,complex)):
						moveList.append(dict({'delay':thisParams['delay']}))

				moveList.append(dict({'speed':theTool['down-plunger-speed']}))

				moveList.append(dict({
					'z':0,
					'container':containerName
					}))

				if 'blowout' in list(thisParams):
					moveList.append(dict({'plunger':'blowout'}))

				if 'touch-tip' in list(thisParams) and 'diameter' in list(locationPos):
					if thisParams['touch-tip'] == True:
						moveList.append(dict({
								'y':locationPos['diameter'] / 2,
								'relative':True
							}))
						moveList.append(dict({
								'y':-locationPos['diameter'],
								'relative':True
							}))
						moveList.append(dict({
								'y':locationPos['diameter'] / 2,
								'relative':True
							}))
						moveList.append(dict({
								'x':locationPos['diameter'] / 2,
								'relative':True
							}))
						moveList.append(dict({
								'x':-locationPos['diameter'],
								'relative':True
							}))
						moveList.append(dict({
								'x':locationPos['diameter'] / 2,
								'relative':True
						}))

		return moveList

	def getPercentage(self, thisVolume, theTool):
		realVolume = float(thisVolume)
		absVolume = abs(realVolume)

		amountToScale = 1

		if absVolume is not None and theTool is not None and 'points' in list(theTool):
			for i in range(len(theTool['points'])-1):
				if absVolume >= theTool['points'][i]['f1'] and absVolume <= theTool['points'][i+1]['f1']:
					f1Diff = theTool['points'][i+1]['f1'] - theTool['points'][i]['f1']
					f1Percentage = (absVolume - theTool['points'][i]['f1']) / f1Diff
					lowerScale = theTool['points'][i]['f1'] / theTool['points'][i]['f2']
					upperScale = theTool['points'][i+1]['f1'] / theTool['points'][i+1]['f2']

					amountToScale = ((upperScale - lowerScale) * f1Percentage) + lowerScale

					break

		absVolume *= amountToScale
		if realVolume < 0:
			absVolume *= -1

		return absVolume / theTool['volume']








