from AirSimClient import *
import cv2
import numpy as np
import time 
import copy

import asynchat
import asyncore
import socket
import threading
# Extra Classes



class Image:
    def __init__(self, image_data, timestamp, camera_position, camera_orientation):
        self.image_data = image_data # will be np.array in form of bgra
        self.timestamp = timestamp
        self.camera_position = camera_position
        self.camera_orientation = camera_orientation

class ImagesInfo:
    def __init__(self, timestamp = None, state = None):
        self.timestamp = timestamp
        self.state = state

class PModHCameraInfo: #PModH => persistent module helper
    def __init__(self, id):
        self._id = id
        intermidiate_map = PModHCameraInfo.get_camera_type_map()
        for k, value in intermidiate_map.items():
            intermidiate_map[k] = [value, 0]
        self._cameraTypeMap = intermidiate_map
        self.requests = []
    
    def update(self):
        # take and return image requests
        self.requests = []
        for k, value in self._cameraTypeMap.items():
            if value[1] > 0:
                pixels_as_float = True if k in ["depth", "depth_planner", "depth_perspective", "disparity"] else False
                self.requests.append([self._id, k, ImageRequest(self._id, value[0], pixels_as_float, False)])
    
    def get_requests(self):
        return self.requests

    def get_id(self):
        return self._id
    
    def add_image_type(self, typename):
        self._cameraTypeMap[typename][1] += 1

    def remove_image_type(self, typename):
        curr_count = self._cameraTypeMap[typename][1]
        if curr_count > 0:
            self._cameraTypeMap[typename][1] = curr_count - 1

    @staticmethod
    def get_camera_type_map():
        return { 
            "depth": AirSimImageType.DepthVis,
            "depth_planner": AirSimImageType.DepthPlanner,
            "depth_perspective": AirSimImageType.DepthPerspective,
            "segmentation": AirSimImageType.Segmentation,
            "scene": AirSimImageType.Scene,
            "disparity": AirSimImageType.DisparityNormalized,
            "normals": AirSimImageType.SurfaceNormals
        }
'''
    Scene = 0
    DepthPlanner = 1
    DepthPerspective = 2
    DepthVis = 3
    DisparityNormalized = 4
    Segmentation = 5
    SurfaceNormals = 6
'''
    
# Persistent ModuleBase
class PModBase:
    def __init__(self, client, persistent_modules):
        self.client = client
        self.persistent_modules = persistent_modules

    def get_name(self):
        raise NotImplementedError
    
    def start(self):
        raise NotImplementedError

    def update(self):
        raise NotImplementedError
    
    def stop(self):
        raise NotImplementedError

class PModConstants(PModBase):
    def __init__(self, client, persistent_modules):
        super().__init__(client, persistent_modules)
        self.standard_speed = 5 # 5m/s

    def get_name(self):
        return 'constants'

    def start(self):
        pass

    def update(self):
        pass

    def stop(self):
        pass

# Persistent Module
class PModMyState(PModBase):
    def __init__(self, client, persistent_modules):
        super().__init__(client, persistent_modules)
        self._state = MultirotorState()
    
    def get_name(self):
        return 'mystate'

    def start(self):
        pass # not required

    def update(self):
        self._state = self.client.getMultirotorState()
    
    def get_state(self):
        return self._state

    def get_position(self):
        return self._state.kinematics_true.position
    
    def get_orientation(self):
        return self._state.kinematics_true.orientation

# Persistent Module 
class PModCamera(PModBase): # PMod => persistent module
    def __init__(self, client, persistent_modules):
        super().__init__(client, persistent_modules)
        self._cameras = [PModHCameraInfo(i) for i in range(5)]
        self._image_dicts = [PModHCameraInfo.get_camera_type_map() for i in range(5)] + [ImagesInfo(), ]
        self._oldimage_dicts = self._image_dicts
        self._num_image_iter = 0

    def get_name(self):
        return 'camera'

    def start(self):
        pass # Change default camera settings here

    def update(self):
        self._num_image_iter += 1

        # Update old images
        self._oldimage_dicts = copy.deepcopy(self._image_dicts)

        # Update all cameras 
        for c in self._cameras:
            c.update()
        
        # Collect all image requests
        requests = []
        requestsinfo = []
        for c in self._cameras:
            for req in c.requests:
                requests.append(req[2])
                requestsinfo.append((req[0], req[1]))

        # Execute all requests
        responses = self.client.simGetImages(requests)
        assert len(responses) == len(requests)

        # Process responces and save in respective dicts
        for n, res in enumerate(responses):
            i, k = requestsinfo[n]
            self._image_dicts[i][k] = self._extract_image(res)

    def _extract_image(self, response):
        img1d = None
        channels = 4
        if (response.image_type in [1, 2, 3, 4]):
            img1d = np.asarray(response.image_data_float, np.float32)
            #print(img1d)
            channels = 1
        else:
            img1d = np.fromstring(response.image_data_uint8, dtype=np.uint8) #get numpy array
        #reshape array to 4 channel image array H X W X channels
        img_rgba = img1d.reshape(response.height, response.width, channels) 
        if channels == 4:
            img_bgra = img_rgba[:,:,[2,1,0,3]]
        else:
            img_bgra = img_rgba
        return Image(img_bgra, response.time_stamp, response.camera_position, response.camera_orientation)
    
    def get_camera(self, camera_id):
        return self._cameras[camera_id]

    def get_image(self, camera_id, image_type):
        img = self._image_dicts[camera_id][image_type]
        if type(img) == Image:
            return img
        else:
            raise ValueError("Image does not exist, did you call add_image_type() on camera " + str(camera_id))

    def get_oldimage(self, camera_id, image_type):
        img = self._oldimage_dicts[camera_id][image_type]
        if type(img) == np.ndarray:
            return img
        else:
            return self.get_image(camera_id, image_type)

    
    def get_image_pair(self, camera_id, image_type):
        return (self.get_image(camera_id, image_type), self.get_oldimage(camera_id, image_type))
        
    ## TODO add other methods of camera orientation etc


# TODO Continue 

# 

# Persistent Module Helper class
class PModHCameraHelper:
    def __init__(self, persistent_modules):
        self.mystate_module = persistent_modules['mystate']
        self.camera_module = persistent_modules['camera']
    
    def update(self):
        self.camera_module._image_dicts[-1].timestamp = time.time()
        self.camera_module._image_dicts[-1].state = self.mystate_module.get_state()


# Dependency Camera Module 
class PModWindowsManager(PModBase):
    def __init__(self, client, persistent_modules):
        super().__init__(client, persistent_modules)
        self.windows = {}
    
    def get_name(self):
        return 'windows_manager'

    def start(self):
        self.camera_module = self.persistent_modules['camera']

    def update(self):
        for k, fun in self.windows.items():
            cv2.imshow(k, fun())

    def add_window_by_camera(self, camera_id, image_type):
        name = "Camera_" + str(camera_id) + "_" + image_type
        self.camera_module.get_camera(camera_id).add_image_type(image_type)
        self.add_window(name, lambda: self.camera_module.get_image(camera_id, image_type).image_data)

    def remove_window_by_camera(self, camera_id, image_type):
        name = "Camera_" + str(camera_id) + "_" + image_type
        self.camera_module.cameras[camera_id].remove_image_type(image_type)
        self.remove_window(name)

    def add_window(self, name, image_function):
        if name in self.windows.keys():
            raise KeyError("Window already exists")
        self.windows[name] = image_function

    def remove_window(self, name):
        self.windows.pop(name, None)

# BaseCmd 
class BaseCmd:
    def __init__(self, client, persistent_modules, modules, line, engage_object):
        self.client = client
        self.persistent_modules = persistent_modules
        self.modules = modules
        self.line = line
        self.engage_object = engage_object
        self.command = line[0]

    def start(self):
        raise NotImplementedError
    
    def update(self):
        raise NotImplementedError

    def get_persistent_module(self, name):
        return self.persistent_modules[name]
    
    # Inheritable Static Method
    def can_process(line):
        raise NotImplementedError

# Cmd
class CmdMove(BaseCmd):
    def __init__(self, client, persistent_modules, modules, line, engage_object = None):
        super().__init__(client, persistent_modules, modules, line, engage_object)
        self.final_location = None
        self.constants_module = self.get_persistent_module('constants')
        # Set default if not specified
        self.distance_param = line[1]
        if self.distance_param == 'null':
            self.distance_param == '1m'
        self.param_mode = self.distance_param[-1] 
        self.distance_param = self.distance_param[:-1]
        if self.param_mode == 's':
            self.distance_param = str(float(self.distance_param) * self.constants_module.standard_speed)
        #print(self.command + " " + self.distance_param)

    def start(self):
        self.mystate_module = self.get_persistent_module('mystate')
        locationVec = list(self.mystate_module.get_position())
        offset = [0, 0, 0]
        print(locationVec)
        # Process command
        yaw = AirSimClientBase.toEulerianAngle(self.mystate_module.get_orientation())[2]
        if self.command == 'up':
            offset[2] -= float(self.distance_param)
        elif self.command == 'down':
            offset[2] += float(self.distance_param)
        elif self.command == 'forward':
            offset[0] += float(self.distance_param) * math.cos(yaw)
            offset[1] += float(self.distance_param) * math.sin(yaw)
        elif self.command == 'backward':
            offset[0] -= float(self.distance_param) * math.cos(yaw)
            offset[1] -= float(self.distance_param) * math.sin(yaw)
        elif self.command == 'right':
            offset[0] += float(self.distance_param) * math.sin(yaw)
            offset[1] += float(self.distance_param) * math.cos(yaw)
        elif self.command == 'left':
            offset[0] -= float(self.distance_param) * math.sin(yaw)
            offset[1] -= float(self.distance_param) * math.cos(yaw)
        
        # add to location
        locationVec[0] += offset[0]
        locationVec[1] += offset[1]
        locationVec[2] += offset[2]
        self.final_location = locationVec
        print(self.final_location)

        # Note that this call is cancellable if other movement related call is called
        self.client.moveToPosition(self.final_location[0], self.final_location[1], self.final_location[2],
            self.constants_module.standard_speed, 0)
    
    def update(self):
        locationVec = list(self.mystate_module.get_position())
        # Check if movement is complete or < 0.5 meters distance, anyway thats offset
        if ((self.final_location[0] - locationVec[0])**2 + (self.final_location[1] - locationVec[1])**2
            + (self.final_location[2] - locationVec[2])**2)**(1/2) < 0.5:
            if self.engage_object:
                self.engage_object.status = 0
                self.engage_object.done = True
            return True
        return False
        
    def can_process(line):
        if line[0] in ['forward', 'backword', 'up', 'down', 'left', 'right']:
            return True
        return False

# Cmd 
class CmdTakePic(BaseCmd):
    def __init__(self, client, persistent_modules, modules, line, engage_object):
        super().__init__(client, persistent_modules, modules, line, engage_object)
        
    def start(self):
        # Engage pic camera front for now
        self.camera_module = self.get_persistent_module('camera')
        self.camera_module.get_camera(0).add_image_type('scene')

    def update(self):
        img = self.camera_module.get_image(0, 'scene') # Returns Image Object
        # do something with image
        # TODO

        # Disengage Camera module
        self.camera_module.get_camera(0).remove_image_type('scene')

        # update engage_object
        self.engage_object.data = img
        self.engage_object.status = True
        self.engage_object.done = True
        return True

    def can_process(line):
        if line[0] in ['camera']:
            return True
        return False

#Cmd 
class CmdReset(BaseCmd):
    def __init__(self, client, persistent_modules, modules, line, engage_object):
        super().__init__(client, persistent_modules, modules, line, engage_object)
    
    def start(self):
        self.mystate_module = self.get_persistent_module('mystate')
        self.constants_module = self.get_persistent_module('constants')
        self.client.moveToPosition(0, 0, 0, self.constants_module.standard_speed, 0)
        self.final_location = [0, 0, 0.68]
    
    def update(self):
        locationVec = list(self.mystate_module.get_position())
        if ((self.final_location[0] - locationVec[0])**2 + (self.final_location[1] - locationVec[1])**2
            + (self.final_location[2] - locationVec[2])**2)**(1/2) < 2:
            return True
        return False
    
    def stop(self):
        pass
    
    def can_process(line):
        if line[0] in ['reset']:
            return True
        return False

#Cmd 
class CmdTakeoff(BaseCmd):
    def __init__(self, client, persistent_modules, modules, line, engage_object):
        super().__init__(client, persistent_modules, modules, line, engage_object)
    
    def start(self):
        self.client.takeoff(8)
    
    def update(self):
        return True
    
    def stop(self):
        pass
    
    def can_process(line):
        if line[0] in ['takeoff']:
            return True
        return False
# 

# Module
class ModBase:
    def __init__(self, client, persistent_modules):
        self.client = client
        self.persistent_modules = persistent_modules
        self.enabled = False
    
    def get_name(self):
        raise NotImplementedError

    def enable(self):
        self.enabled = True
    
    def disable(self):
        self.enabled = False

    def update(self):
        raise NotImplementedError

class EngageObject:
    def __init__(self, id, addr = None):
        self.addr = addr
        self.data = b''
        self.id = id
        self.status = -1
        self.done = False

class ChatHandler(asynchat.async_chat):
    def __init__(self, sock, addr, callback, chat_room):
        asynchat.async_chat.__init__(self, sock=sock, map=chat_room)
        self.addr = addr
        self.set_terminator(b'\r\nDONEPACKET\r\n')
        self.buffer = []
        self.callback = callback
 
    def collect_incoming_data(self, data):
        self.buffer.append(data.decode('ASCII'))
 
    def found_terminator(self):
        msg = ''.join(self.buffer)
        print('Received: %s'% msg)
        msg = msg.split(" ")

        engage_object = EngageObject(msg[0], self.addr)

        self.callback(msg[1:], engage_object)
        # for handler in chat_room.values():
        #     if hasattr(handler, 'push'):
        #         handler.push((msg + '\n').encode('ASCII'))
        self.buffer = []

class ChatServer(asyncore.dispatcher):
    def __init__(self, host, port, handler, chat_room):
        asyncore.dispatcher.__init__(self, map=chat_room)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bind((host, port))
        self.listen(5)
        self.res_handler = handler
        self.chat_room = chat_room
 
    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            print('Incoming connection from %s' % repr(addr))
            handler = ChatHandler(sock, addr, self.res_handler, self.chat_room)
            handler.push("Hello".encode("ASCII") + b'\r\nDONEPACKET\r\n')

class ModCommandServer(ModBase):
    def __init__(self, client, persistent_modules, add_command):
        super().__init__(client, persistent_modules)
        self.add_command = add_command

        self.engage_object_list = []
        self.chat_room = {}

    def get_name(self):
        return 'command_server'

    def enable(self):
        super().enable()
        self.server = ChatServer('localhost', 5050, self.process, self.chat_room)
        self.comm = threading.Thread(target= lambda: (asyncore.loop(map=self.chat_room)))
        self.comm.daemon = True
        self.comm.start()
        print('Serving command API on localhost:5050')

    def disable(self):
        super().disable()
        # Note that this only stops update and not disable server

    # Only test method
    def later(self, msg, engage_object):
        time.sleep(2)
        engage_object.data = (str(engage_object.id) + ' done').encode('ASCII')
        engage_object.status = 0
        engage_object.done = True

    def start(self):
        pass

    def process(self, msg, engage_object):

        # if server is disabled return msg with fail
        if (not self.enabled):
            engage_object.data = b"Failed: ModCommandServer disabled"
            engage_object.status = -1
            engage_object.done = True
            return
        
        # else
        print("Processing command " + str(msg))
        self.engage_object_list.append(engage_object)
        # replace here with add_command
        #threading.Thread(target=lambda: self.later(msg, engage_object)).start()
        self.add_command(msg, engage_object)


    def update(self):
        #print("dispatching")
        delete_list = []
        for e in self.engage_object_list:
            if e.done == True:
                for handler in self.chat_room.values():
                    if hasattr(handler, 'push'):
                        packetstr = e.id + " " + str(e.status) + " "
                        packet = packetstr.encode('ASCII') + e.data + b'\r\nDONEPACKET\r\n'
                        handler.push(packet)
                delete_list.append(e)
        for e in delete_list:
            self.engage_object_list.remove(e)



# Main Controller
class Controller:
    def __init__(self, persistent_module_classes, persistent_module_helper_classes, module_classes):
        # Connect Simulator
        self.client = MultirotorClient()
        self.client.confirmConnection()
        self.client.enableApiControl(True)

        # Persistent Modules
        self.persistent_modules = {}
        
        for c in persistent_module_classes:
            self.persistent_modules[c.get_name()] = c(self.client, self.persistent_modules)

        # start all persistent modules
        for k, mod in self.persistent_modules.items():
            mod.start()
        # Persistent Module Helpers
        self.persistent_module_helpers = {}
        self.persistent_module_helpers['camera_helper'] = PModHCameraHelper(self.persistent_modules)

        # Modules 
        self.modules = {}
        for c in module_classes:
            self.modules[c.get_name()] = c(self.client, self.persistent_modules, self.add_command)
        
        # Commands
        self.commands = []
        self.commands_buffer = []

        # Vars
        self._iteration = 0

        # Command Classes
        self.command_classes = [
            CmdMove, CmdReset, CmdTakeoff, CmdTakePic
        ]

        # Test
        self.modules['command_server'].enable()
        self.persistent_modules['windows_manager'].add_window_by_camera(0, 'scene')
        self.persistent_modules['windows_manager'].add_window_by_camera(0, 'depth')
        #self.persistent_modules['windows_manager'].add_window_by_camera(0, 'depth_perspective')

        #self.commands_buffer.append(CmdReset(self.client, self.persistent_modules, self.modules, ['reset', ''], None))
        #self.commands_buffer.append(CmdTakeoff(self.client, self.persistent_modules, self.modules, ['takeoff', ''], None))
        self.commands_buffer.append(CmdMove(self.client, self.persistent_modules, self.modules, ['up', '15m'], None))
        #self.commands_buffer.append(CmdMove(self.client, self.persistent_modules, self.modules, ['left', '69m'], None))
        #self.commands_buffer.append(CmdMove(self.client, self.persistent_modules, self.modules, ['down', '3m'], None))
        # End Test


    def _get_command_object(self, line):
        cmd = None
        for c in self.command_classes:
            if c.can_process(line):
                cmd = c(self.client, self.persistent_modules, self.modules, line, None) # TODO Change engage object here
        return cmd

    # TODO update this, its a bad practice to assume that it will work -,-, be optimistic though ;)
    def add_command(self, line, engage_object = None):
        cmd = self._get_command_object(line)
        if cmd is None:
            return 
        elif type(cmd) in [CmdMove,]:
            print("Detected a move command " + str(line))
            self.commands_buffer.append(cmd)
        else:
            self.commands.append(cmd)
        return True

    def control(self):
        print(list(self.persistent_modules['mystate'].get_position()))
        t_old = time.time()
        while(True):
            self._iteration += 1

            if self._iteration % 100 == 0:
                d_time = time.time() - t_old
                print(str(self._iteration) + " " + str(100/d_time) + " " + 
                    str(list(self.persistent_modules['mystate'].get_position())))
                t_old = time.time()
            # Update persistent modules
            for k in self.persistent_modules.keys():
                self.persistent_modules[k].update()

            # Update persistent module helpers
            for k, mod in self.persistent_module_helpers.items():
                    mod.update()

            # Update current commands
            cpoplist = []
            for c in self.commands:
                ans = c.update()
                if ans == True:
                    print(list(self.persistent_modules['mystate'].get_position()))
                    cpoplist.append(c)
            for c in cpoplist:
                self.commands.remove(c)

            # Add new commands if any
            if len(self.commands) == 0:
                cmd = 0
                try:
                    cmd = self.commands_buffer.pop(0)
                except IndexError:
                    pass
                if cmd != 0:
                    print("cmd" + cmd.command)
                    cmd.start()
                    self.commands.append(cmd)

            # Add for cv2.imshow() to work
            key = cv2.waitKey(1) & 0xFF
            if (key == 27 or key == ord('q') or key == ord('x')):
                break

persistent_module_classes = [PModConstants, PModMyState, PModCamera, PModWindowsManager]
persistent_module_helper = [PModHCameraHelper,]
module_classes = [ModCommandServer,]

ctrl = Controller(persistent_module_classes, persistent_module_helper_classes, module_classes)
ctrl.control()

'''
Controller
HTTPServer

Mystate

CameraFeed
Stabilize
DQN

Debug
ModWindowsManager
Logging
'''