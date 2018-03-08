"""
For connecting to the AirSim drone environment and testing API functionality
"""

import os
import tempfile
import pprint
import cv2

from AirSimClient import *


# connect to the AirSim simulator
client = MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

state = client.getMultirotorState()
s = pprint.pformat(state)
print("state: %s" % s)
print("pry: %s" % str(AirSimClientBase.toEulerianAngle(state.kinematics_true.orientation))) 
AirSimClientBase.wait_key('Press any key to takeoff')
#client.takeoff()

state = client.getMultirotorState()
print("state: %s" % pprint.pformat(state))


AirSimClientBase.wait_key('Press any key to move vehicle to (-10, 10, -10) at 5 m/s')
client.moveToPosition(-10, 10, -10, 5, 0)
print("returned instantly")

state = client.getMultirotorState()
print("state: %s" % pprint.pformat(state))

AirSimClientBase.wait_key('Press any key to take images')
# get camera images from the car
responses = client.simGetImages([
    ImageRequest(0, AirSimImageType.DepthVis),  #depth visualiztion image
    ImageRequest(1, AirSimImageType.DepthPerspective, True), #depth in perspective projection
    ImageRequest(1, AirSimImageType.Scene), #scene vision image in png format
    ImageRequest(1, AirSimImageType.DepthVis, False, False)])  #scene vision image in uncompressed RGBA array
print('Retrieved images: %d' % len(responses))

tmp_dir = os.path.join(tempfile.gettempdir(), "airsim_drone")
print ("Saving images to %s" % tmp_dir)
try:
    os.makedirs(tmp_dir)
except OSError:
    if not os.path.isdir(tmp_dir):
        raise
print("data: " + str(len(responses[3].image_data_uint8)))
img1d = np.fromstring(responses[3].image_data_uint8, dtype=np.uint8) #get numpy array
img_rgba = img1d.reshape(responses[3].height, responses[3].width, 4) #reshape array to 4 channel image array H X W X 4
print(img_rgba.shape)
img_rgba = img_rgba[:,:,[2,1,0,3]]
print(img_rgba.shape)
#img_rgba = np.flipud(img_rgba) #original image is fliped vertically
#img_rgba[:,:,1:2] = 100 #just for fun add little bit of green in all pixels
cv2.imshow("1", img_rgba)
cv2.waitKey(1)

for idx, response in enumerate(responses):

    filename = os.path.join(tmp_dir, str(idx))

    if response.pixels_asat:
        print("Type %d, size %d" % (response.image_type, len(response.image_data_float)))
        AirSimClientBase.write_pfm(os.path.normp_floath(filename + '.pfm'), AirSimClientBase.getPfmArray(response))
    elif response.compress: #png format
        print("Type %d, size %d" % (response.image_type, len(response.image_data_uint8)))
        AirSimClientBase.write_file(os.path.normpath(filename + '.png'), response.image_data_uint8)
    else: #uncompressed array
        print("Type %d, size %d" % (response.image_type, len(response.image_data_uint8)))
        img1d = np.fromstring(response.image_data_uint8, dtype=np.uint8) #get numpy array
        img_rgba = img1d.reshape(response.height, response.width, 4) #reshape array to 4 channel image array H X W X 4
        img_rgba = np.flipud(img_rgba) #original image is fliped vertically
        img_rgba[:,:,1:2] = 100 #just for fun add little bit of green in all pixels
        AirSimClientBase.write_png(os.path.normpath(filename + '.greener.png'), img_rgba) #write to png

AirSimClientBase.wait_key('Press any key to reset to original state')
AirSimClientBase.wait_key('Press any key to reset to original state')
state = client.getMultirotorState()
print("state: %s" % pprint.pformat(state))
AirSimClientBase.wait_key('Press any key to reset to original state')
client.reset()

# that's enough fun for now. let's quit cleanly
client.enableApiControl(False)
input()