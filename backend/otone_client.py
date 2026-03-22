#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created on Fri Apr 24 15:11:09 2015

@author: Randy

This is the main module of the OTOne Python backend code. When started, it creates 
a publisher (:class:`publisher.Publisher`) and a subscriber (:class:`subscriber.Subscriber`)
for handling all communication with a WAMP router and then tries to make a connection 
(:meth:`otone_client.make_a_connection`) with the Crossbar.io WAMP router. Once that 
connection is established, it instantiates and configures various objects with 
:meth:`otone_client.instantiate_objects`:
 
 head: :class:`head.Head` - Represents the robot head and creates a connection with Smoothieboard
 
 deck: :class:`deck.Deck` - Represents the robot deck

 runner: :class:`protocol_runner.ProtocolRunner` - Runs protocol jobs

 the_sk: :class:`script_keeper.ScriptKeeper` - Handles shell scripts


"""

#import RobotLib
import json, asyncio, sys, time, collections, os, sys, shutil
import uuid
import copy

from head import Head
from deck import Deck

from subscriber import Subscriber
from publisher import Publisher

from file_io import FileIO
from ingredients import Ingredients

from protocol_runner import ProtocolRunner

import script_keeper as sk
from script_keeper import ScriptKeeper


debug = True
verbose = False

#VARIABLES

#declare globol objects here
#head = None
#deck = None
#runner = None
#subscriber = None
#publisher = None
#def_start_protocol = None
#client_status = False
#crossbar_status = False

if debug == True: FileIO.log('starting up')
#for testing purposes, read in a protocol.json file
path = os.path.abspath(__file__)
dir_path = os.path.dirname(path)
dir_par_path = os.path.dirname(dir_path)
dir_par_par_path = os.path.dirname(dir_par_path)
fname_default_protocol = os.path.join(dir_path,'data/sample_user_protocol.json')
fname_default_containers = os.path.join(dir_path, 'data/containers.json')
fname_default_calibrations = os.path.join(dir_path, 'data/pipette_calibrations.json')
fname_default_settings = os.path.join(dir_path, 'data/settings.json')
fname_data = os.path.join(dir_par_par_path,'otone_data')
fname_data_containers = os.path.join(dir_par_par_path,'otone_data/containers.json')
fname_data_calibrations = os.path.join(dir_par_par_path, 'otone_data/pipette_calibrations.json')
fname_data_settings = os.path.join(dir_par_par_path, 'otone_data/settings.json')
print('dir_path: ', dir_path)
print('dir_par_path: ', dir_par_path)
print('dir_par_part_path: ', dir_par_par_path)
print('fname_data: ', fname_data)
print('fname_default_containers: ', fname_default_containers)
print('fname_data_containers: ', fname_data_containers)



if not os.path.isdir(fname_data):
    os.makedirs(fname_data)
#if not os.path.exists(fname_data_containers):
open(fname_data_containers,"w+")
shutil.copy(fname_default_containers, fname_data_containers)

if not os.path.exists(fname_data_calibrations):
    open(fname_data_calibrations,"w+")
    shutil.copy(fname_default_calibrations, fname_data_calibrations)

#if not os.path.exists(fname_data_settings):
#    open(fname_data_settings,"w+")
#    shutil.copy(fname_default_settings, fname_data_settings)

prot_dict = FileIO.get_dict_from_json(fname_default_protocol)



#Import and setup autobahn WAMP peer
from autobahn.asyncio import wamp, websocket

class WampComponent(wamp.ApplicationSession):
    """WAMP application session for OTOne (Overrides protocol.ApplicationSession - WAMP endpoint session)
    """

    def onConnect(self):
        """Callback fired when the transport this session will run over has been established.
        """
        self.join(u"ot_realm")

    @asyncio.coroutine
    def onJoin(self, details):
        """Callback fired when WAMP session has been established.

        May return a Deferred/Future.

        Starts instatiation of robot objects by calling :meth:`otone_client.instantiate_objects`.
        """
        if debug == True: FileIO.log('otone_client : WampComponent.onJoin called','\n\targs: ',locals(),'\n')
        if not self.factory._myAppSession:
            self.factory._myAppSession = self
        try:
            self.factory._crossbar_connected = True
            FileIO.log('CONNECT SMOOTHIE - otone_client.head.smoothieAPI.connect()')
            self.factory._head.smoothieAPI.connect()
        except AttributeError:
            FileIO.log('ERROR: factory does not have "crossbar_connected" attribute')

        #instantiate_objects()
        
        
        def handshake(client_data):
            """Hook for factory to call _handshake()
            """
            FileIO.log('otone_client : WampComponent.handshake:\n\targs: ',locals(),'\n')
            try:
                self.factory._handshake(client_data)
            except AttributeError:
                FileIO.log('ERROR: factory does not have "_handshake" attribute')


        def dispatch_message(client_data):
            """Hook for factory to call dispatch_message()
            """
            FileIO.log('otone_client : WampComponent.dispatch_message:\n\targs: ',locals(),'\n')
            try:
                self.factory._dispatch_message(client_data)
            except AttributeError:
                FileIO.log('ERROR: factory does not have "_dispatch_message" attribute')

        yield from self.subscribe(handshake, 'com.opentrons.browser_ready')
        yield from self.subscribe(dispatch_message, 'com.opentrons.browser_to_robot')


    def onLeave(self, details):
        """Callback fired when WAMP session has been closed.
        
        :param details: Close information.
        """
        if self.factory._myAppSession == self:
            self.factory._myAppSession = None
        try:
            self.disconnect()
        except:
            pass
        
    def onDisconnect(self):
        """Callback fired when underlying transport has been closed.
        """
        asyncio.get_event_loop().stop()



class OTOneClient():
    def __init__(self):
        FileIO.log('OTClient.__init__')

        self.clients = {
            # uuid : 'com.opentrons.[uuid]'
        }
        self.max_clients = 4

        self.id = str(uuid.uuid4())

        self.session_factory = wamp.ApplicationSessionFactory()
        self.session_factory.session = WampComponent
        self.session_factory._myAppSession = None
        self.session_factory._crossbar_connected = False
        self.transport_factory = None

        self.transport = None
        self.protocol = None

        def_start_protocol = FileIO.get_dict_from_json(os.path.join(dir_path,'data/default_startup_protocol.json'))
        self.head = Head(def_start_protocol, self)
        self.sk = ScriptKeeper(self)
        self.runner = ProtocolRunner(self.head, self)

        # FROM subscriber
        FileIO.log('self.in_dispatcher')
        self.in_dispatcher = {
            'home' : lambda self, data: self.home(data), #x
            'stop' : lambda self, data: self.head.theQueue.kill(data), #-
            'reset' : lambda self, data: self.reset(data), #x
            'move' : lambda self, data: self.head.move(data), #-
            'step' : lambda self, data: self.head.step(data), #-
            'calibratePipette' : lambda self, data: self.calibrate_pipette(data), #x
            'calibrateContainer' : lambda self, data: self.calibrate_container(data), #x
            'getCalibrations' : lambda self, data: self.get_calibrations(data), #x
            'getContainers' : lambda self, data: self.get_containers(data), #x
            'containerDepthOverride': lambda self, data: self.container_depth_override(data),
            'saveVolume' : lambda self, data: self.head.save_volume(data), #-
            'movePipette' : lambda self, data: self.move_pipette(data), #x
            'movePlunger' : lambda self, data: self.move_plunger(data), #x
            'speed' : lambda self, data: self.speed(data), #x
            'createDeck' : lambda self, data: self.create_deck(data), #x
            'configureHead' : lambda self, data: self.configure_head(data), #x
            'relativeCoords' : lambda self, data: self.head.relative_coords(data), #-
            'instructions' : lambda self, data: self.instructions(data), #x
            'infinity' : lambda self, data: self.infinity(data), #x
            'pauseJob' : lambda self, data: self.head.theQueue.pause_job(data), #-
            'resumeJob' : lambda self, data: self.head.theQueue.resume_job(data), #-
            'eraseJob' : lambda self, data: self.runner.insQueue.erase_job(data), #-
            'raw' : lambda self, data: self.head.raw(data), #-
            'update' : lambda self, data: self.loop.create_task(self.update(data)), #x
            'wifimode' : lambda self, data: self.wifi_mode(data), #x
            'wifiscan' : lambda self, data: self.wifi_scan(data), #x
            'hostname' : lambda self, data: self.change_hostname(data), #x
            'poweroff' : lambda self, data: self.poweroff(data), #x
            'reboot' : lambda self, data: self.reboot(data), #x
            'restart' : lambda self, data: self.restart(data), #x
            'shareinet': lambda self, data: self.loop.create_task(self.share_inet(data)) #x
        }

        self.loop = asyncio.get_event_loop()

        

        

    def handshake(self, data):
        FileIO.log('OTOneClient.handshake:\n\targs: ',locals(),'\n')
        #data_dict = json.loads(data)
        FileIO.log('handshake data: ',data)
        self.session_factory._myAppSession.publish('com.opentrons.robot_ready',True)


    # FROM subscriber
    def dispatch_message(self, message):
        """The first point of contact for incoming messages.
        """
        if debug == True: FileIO.log('otone_client.dispatch_message:\nargs: ',locals(),'\n')
        try:
            dictum = collections.OrderedDict(json.loads(message.strip(), object_pairs_hook=collections.OrderedDict))
            FileIO.log('dictum: ',dictum)
            if 'data' in dictum:
                if debug == True: FileIO.log('\tdictum[data]:\n\n',dictum['data'])
                #json.dumps(dictum['data'],sort_keys=True,indent=4,separators=(',',': ')),'\n')
                self.in_dispatcher[dictum['type']](dictum['data'])
            else:
                dictum['data'] = 'wtf'
                FileIO.log(self.in_dispatcher[dictum['type']])
                self.in_dispatcher[dictum['type']](self, dictum['data'])
        except:
            FileIO.log('*** error in otone_client.dispatch_message ***\n',sys.exc_info())
            raise
            #PUBLISH ERROR

    def home(self, data):
        """Intermediate step to start a homing sequence
        """
        if debug == True: FileIO.log('otone_client.home:\nargs: ',locals(),'\n')
        self.runner.insQueue.infinity_data = None
        self.runner.insQueue.erase_job()
        self.head.home(data)

    def reset(self, data):
        """Intermediate step to reset Smoothieboard
        """
        if debug == True: FileIO.log('subscriber.reset called')
        self.runner.insQueue.infinity_data = None
        self.head.theQueue.reset()

    def calibrate_pipette(self, data):
        """Tell the :head:`head` to calibrate a :class:`pipette`
        """
        if debug == True:
            FileIO.log('subscriber.calibrate_pipette called')
            if verbose == True: FileIO.log('\nargs: ', data,'\n')
        if 'axis' in data and 'property' in data:
            axis = data['axis']
            property_ = data['property']
            value = data.get('value',None)
            self.head.calibrate_pipette(axis, property_, value)
        self.get_calibrations(data)

    def calibrate_container(self, data):
        """Tell the :class:`head` to calibrate a container
        """
        if debug == True:
            FileIO.log('subscriber.calibrate_container called')
            if verbose == True: FileIO.log('\nargs: ', data,'\n')
        if 'axis' in data and 'name' in data:
            axis = data['axis']
            container_ = data['name']
            self.head.calibrate_container(axis, container_)
        self.get_calibrations(data)

    def get_calibrations(self, data):
        """Tell the :class:`head` to publish calibrations
        """
        if debug == True: FileIO.log('subscriber.get_calibrations called')
        self.head.publish_calibrations()

    def get_containers(self, data):
        self.deck.publish_containers()

    def container_depth_override(self, data):
        FileIO.log('subscriber.container_depth_override called')
        container_name = data['name']
        new_depth = data['depth']
        self.deck.container_depth_override(container_name,new_depth)

    def move_pipette(self, data):
        """Tell the :class:`head` to move a :class:`pipette` 
        """
        if debug == True: FileIO.log('subscriber.move_pipette called')
        axis = data['axis']
        property_ = data['property']
        self.head.move_pipette(axis, property_)

    def move_plunger(self, data):
        """Tell the :class:`head` to move a :class:`pipette` to given location(s)
        """
        if debug == True:
            FileIO.log('subscriber.move_plunger called')
            if verbose == True: FileIO.log('\ndata:\n\t',data,'\n')
        self.head.move_plunger(data['axis'], data['locations'])

    def speed(self, data):
        """Tell the :class:`head` to change speed
        """
        if debug == True:
            FileIO.log('subscriber.speed called')
            if verbose == True: FileIO.log('\ndata:\n\t',data,'\n')
        axis = data['axis']
        value = data['value']
        if axis=='ab':
            self.head.set_speed('a', value)
            self.head.set_speed('b', value)
        else:
            self.head.set_speed(axis, value)

    def create_deck(self, data):
        """Intermediate step to have :class:`head` load deck data and return deck information back to Browser

        :todo:
        move publishing into respective objects and have those objects use :class:`publisher` a la :meth:`get_calibrations` (:meth:`create_deck`, :meth:`wifi_scan`)
        """
        if debug == True:
            FileIO.log('subscriber.create_deck called')
            if verbose == True: FileIO.log('\targs: ', data,'\n')
        msg = {
            'type' : 'containerLocations',
            'data' : self.head.create_deck(data)
        }
        if debug == True and verbose == True: FileIO.log('pre-call self.caller._myAppSession.publish() ',json.dumps(msg,sort_keys=True,indent=4,separators=(',',': ')),'\n')
        self.caller._myAppSession.publish('com.opentrons.robot_to_browser',json.dumps(msg,sort_keys=True,indent=4,separators=(',',': ')))

    def configure_head(self, data):
        if debug == True:
            FileIO.log('subscriber.configure_head called')
            if verbose == True: FileIO.log('\targs: ', data,'\n')
        self.head.configure_head(data)


    def instructions(self, data):
        """Intermediate step to have :class:`prtocol_runner` and :class:`the_queue` start running a protocol
        """
        if debug == True:
            FileIO.log('subscriber.instructions called')
            if verbose == True: FileIO.log('\targs: ', data,'\n')
        if data and len(data):
            self.runner.insQueue.start_job (data, True)

    def infinity(self, data):
        """Intermediate step to have :class:`protocol_runner` and :class:`the_queue` run a protocol to infinity and beyond
        """
        if debug == True: FileIO.log('subscriber.infinity called')
        if data and len(data):
            self.runner.insQueue.start_infinity_job (data)

    @asyncio.coroutine
    def update(self, data):
        """Intermediate step to have :class:`script_keeper` run update shell scripts
        """
        if debug == True: FileIO.log('subscriber.update called')
        if data == "all":
            #fut = self.loop.create_task(sk.cool_update('data',total=61))
            #try:
            #    yield from asyncio.wait_for(fut,60)
            #except asyncio.TimeoutError:
            #    failure_string = '!ot!update!failure!msg:'+data+'update timed out'
            #    sk.read_progress(failure_string)
            fut = self.loop.create_task(sk.cool_update('otone_scripts',start=12,total=72))
            try:
                yield from asyncio.wait_for(fut,60)
            except asyncio.TimeoutError:
                failure_string = '!ot!update!failure!msg:'+data+'update timed out'
                sk.read_progress(failure_string)
            fut = self.loop.create_task(sk.cool_update('otone_backend',start=24,total=72))
            try:
                yield from asyncio.wait_for(fut,60)
            except asyncio.TimeoutError:
                failure_string = '!ot!update!failure!msg:'+data+'update timed out'
                sk.read_progress(failure_string)
            #fut = self.loop.create_task(sk.cool_update('central',start=36,total=72))
            #try:
            #    yield from asyncio.wait_for(fut,60)
            #except asyncio.TimeoutError:
            #    failure_string = '!ot!update!failure!msg:'+data+'update timed out'
            #    sk.read_progress(failure_string)
            fut = self.loop.create_task(sk.cool_update('otone_frontend',start=48,total=72))
            try:
                yield from asyncio.wait_for(fut,60)
            except asyncio.TimeoutError:
                failure_string = '!ot!update!failure!msg:'+data+'update timed out'
                sk.read_progress(failure_string)
            fut = self.loop.create_task(sk.cool_update('otone_firmware',start=60,total=72))
            try:
                yield from asyncio.wait_for(fut,60)
            except asyncio.TimeoutError:
                failure_string = '!ot!update!failure!msg:'+data+'update timed out'
                sk.read_progress(failure_string)
            if sk.updated == True:
                subprocess.call(['sudo','reboot'])
        else:
            fut = self.loop.create_task(sk.cool_update(data,action='START'))
            try:
                yield from asyncio.wait_for(fut,60)
            except asyncio.TimeoutError:
                failure_string = '!ot!update!failure!msg:'+data+'update timed out'
                sk.read_progress(failure_string)
        #sk.update(data)

    def wifi_mode(self, data):
        """Intermediate step to have :class:`script_keeper` run shell scripts to change WiFi mode
        """
        if debug == True: FileIO.log('subscriber.wifi_mode called')
        sk.change_wifi_mode(data)

    def wifi_scan(self, data):
        """Intermediate step to have :class:`script_keeper` run scripts to scan WiFi networks
        """
        if debug == True: FileIO.log('subscriber.wifi_mode called')
        ws = collections.OrderedDict(sk.wifi_scan(data))
        self.caller._myAppSession.publish('com.opentrons.robot_to_browser',json.dumps(ws,sort_keys=True,indent=4,separators=(',',': ')))

    def change_hostname(self, data):
        """Intermediate step to have :class:`script_keeper` run shell scripts to change Raspberry Pi hostname
        """
        if debug == True: FileIO.log('subscriber.change_hostname called')
        sk.change_hostname(data)

    def poweroff(self, data):
        """Intermediate step to have :class:`script_keeper` poweroff Raspberry Pi
        """
        if debug == True: FileIO.log('subscriber.poweroff called')
        sk.poweroff()

    def reboot(self, data):
        """Intermediate step to have :class:`script_keeper` reboot Raspberry Pi
        """
        if debug == True: FileIO.log('subscriber.reboot called')
        sk.reboot()

    def restart(self, data):
        """Intermediate step to have :class:`script_keeper` restart Crossbar.io and Python Code
        """
        if debug == True: FileIO.log('subscriber.restart called')
        sk.restart()

    @asyncio.coroutine
    def share_inet(self, data):
        """Intermediate step to have :class:`script_keeper` run a script to have Raspberry Pi ethernet interface obtain an ip address
        """
        if debug == True: FileIO.log('subscriber.share_inet called')
        FileIO.log('subscriber.share_inet called')
        yield from sk.share_inet()


    #FROM publisher
    #Handlers
    def on_smoothie_connect(self):
        """Publish that Smoothieboard is connected
        """
        if debug == True: FileIO.log('publisher.on_smoothie_connect called')
        self.send_message('status',{'string':'Connected to the Smoothieboard','color':'green'})

    def on_smoothie_disconnect(self):
        """Publish that Smoothieboard is disconnected and try to reconnect
        """
        if debug == True: FileIO.log('publisher.on_smoothie_disconnect called')
        self.send_message('status',{'string':'Smoothieboard Disconnected','color':'red'})
        self.head.smoothieAPI.connect()#self.onSmoothieConnect, self.onSmoothieDisconnect)
    
    #originally in app.js
    def on_start(self):  #called from planner/theQueue
        """Publish that theQueue started a command
        """
        if debug == True: FileIO.log('publisher.on_start called')
        self.send_message('status',{'string':'Robot is moving','color':'orange'})

    def on_raw_data(self,string):     #called from smoothie/createSerialConnection
        """
        Publish raw data from Smoothieboard
        """
        if debug == True and verbose == True: FileIO.log('publisher.on_raw_data called')
        self.send_message('smoothie',{'string':string})

    def on_position_data(self,string):
        """
        Publish position data from Smoothieboard
        """
        if debug == True and verbose == True: FileIO.log('publisher.on_position_data called')
        self.send_message('position',{'string':string})

    def on_limit_hit(self,axis):
        """Publish that a limit switch was hit
        """
        if debug == True: FileIO.log('publisher.on_limit_hit called')
        self.send_message('limit',axis)
        
    def on_finish(self):     #called from planner/theQueue
        """Publish status and move on to next instruction step
        """
        if debug == True: FileIO.log('publisher.on_finish called')
        self.send_message('status',{'string':'Robot stopped','color':'black'})
        try:
            self.runner.insQueue.ins_step() #changed name 
        except AttributeError as ae:
            print(ae)

    def show_delay(self, time_left):
        self.send_message('delay',time_left)

    #OTHER DATA NEEDING TO GO BACK TO UI
    def finished(self):
        """Publish that instruction queue finished
        """
        if debug == True: FileIO.log('publisher.finished called')
        self.send_message('finished',None)

    def send_message(self,type_,damsg):
        """Send a message
        """
        if debug == True and verbose == True: FileIO.log('publisher.send_message called')
        if damsg is not None:
            msg = {
                'type':type_,
                'data':damsg
            }
        else:
            msg = {
                'type':type_
            }
        if self.session_factory is not None:
            if self.session_factory._myAppSession is not None:
                try:
                    self.session_factory._myAppSession.publish('com.opentrons.robot_to_browser',json.dumps(msg))
                except:
                    FileIO.log('error trying to send_message:\n',sys.exc_info())
            else:
                FileIO.log('session_factory._myAppSession is None')
        else:
            FileIO.log('session_factory is None')

    def _make_connection(self, url_protocol='ws', url_domain='127.0.0.1', url_port=8080, url_path='ws', debug=False, debug_wamp=False):
        FileIO.log('OTOneClient._make_connection:\n\targs: ',locals(),'\n')
        if self.loop.is_running():
            FileIO.log('self.loop is running. stopping loop now')
            self.loop.stop()
        FileIO.log(self.transport_factory)
        FileIO.log('about to create_connection')
        coro = self.loop.create_connection(self.transport_factory, url_domain, url_port)
        self.transport, self.protocol = self.loop.run_until_complete(coro)
        #protocoler.set_outer(self)
        if not self.loop.is_running():
            FileIO.log('about to call self.loop.run_forever()')
            self.loop.run_forever()

    def connect(self, url_protocol='ws', url_domain='127.0.0.1', url_port=8080, url_path='ws', debug=False, debug_wamp=False, keep_trying=True, period=30):
        FileIO.log('OTOneClient.connect:\n\targs: ',locals(),'\n')
        if self.transport_factory is None:
            url = url_protocol+"://"+url_domain+':'+str(url_port)+'/'+url_path

            self.transport_factory = websocket.WampWebSocketClientFactory(self.session_factory,
                                                                            url=url,
                                                                            debug=debug,
                                                                            debug_wamp=debug_wamp)

        self.session_factory._head = self.head
        self.session_factory._handshake = self.handshake
        self.session_factory._dispatch_message = self.dispatch_message

        if not keep_trying:
            try:
                print('\nClient attempting crossbar connection\n')
                self._make_connection()
            except:
                print('crossbar connection attempt error:\n',sys.exc_info())
                pass
        else:
            time.sleep(60)
            while True:
                while (self.session_factory._crossbar_connected == False):
                    try:
                        print('\nClient attempting crossbar connection\n')
                        self._make_connection()
                    except KeyboardInterrupt:
                        self.session_factory._crossbar_connected = True
                    except:
                        print('crossbar connection attempt error:\n',sys.exc_info())
                        pass
                    finally:
                        print('\nDriver connection failed, sleeping for ',period,' seconds\n')
                        time.sleep(period)





#def make_a_connection():
#    """Attempt to create streaming transport connection and run event loop
#    """
#    coro = loop.create_connection(transport_factory, '127.0.0.1', 8080)
#
#    transporter, protocoler = loop.run_until_complete(coro)
#    #instantiate the subscriber and publisher for communication
#    
#    loop.run_forever()



#try:
#    session_factory = wamp.ApplicationSessionFactory()
#    session_factory.session = WampComponent
#
#    session_factory._myAppSession = None
#
#    url = "ws://127.0.0.1:8080/ws"
#    transport_factory = websocket \
#            .WampWebSocketClientFactory(session_factory,
#                                        url=url,
#                                        debug=False,
#                                        debug_wamp=False)
#    loop = asyncio.get_event_loop()

#    subscriber = Subscriber(session_factory, loop)
#    publisher = Publisher(session_factory)
    

#    while (crossbar_status == False):
#        try:
#            FileIO.log('trying to make a connection...')
#            make_a_connection()
#        except KeyboardInterrupt:
#            crossbar_status = True
#        except:
#            #raise
#            pass
#        finally:
#            FileIO.log('error while trying to make a connection, sleeping for 5 seconds')
#            time.sleep(5)
#except KeyboardInterrupt:
#    pass
#finally:
#    loop.close()


if __name__ == '__main__':
    try:
        FileIO.log('\nBEGIN INIT...\n')
        FileIO.log('INITIAL SETUP - otone_client = OTOneClient()')
        otone_client = OTOneClient()
        #FileIO.log('CONNECT SMOOTHIE - otone_client.head.smoothieAPI.connect()')
        #otone_client.head.smoothieAPI.connect()
        FileIO.log('CONNECT TO CROSSBAR - otone_client.connect()')
        otone_client.connect()
    except KeyboardInterrupt:
        pass
    finally:
        FileIO.log('ALL DONE!')






