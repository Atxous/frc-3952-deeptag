import cv2
from deeptag_model_setting import load_deeptag_models
from marker_dict_setting import load_marker_codebook
from stag_decode.detection_engine import DetectionEngine 
import json
import os
import torch_tensorrt
import torch
import ntcore

#torch_tensorrt.logging.set_reportable_log_level(torch_tensorrt.logging.Level.Debug)

# Compilation process

class Same(torch.nn.Module):
  def __init__(self):
    super().__init__()
  
  def forward(self, x):
    return x


if __name__ == "__main__":
    inst = ntcore.NetworkTableInstance.getDefault()
    table = inst.getTable("jason")
    pose_topic = table.getTopic("tagPose")

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, default='./config_video.json', help='path of configuration file for camera params and marker size')
    parser.add_argument('--CPU', action='store_true', help='use CPU only')
    args = parser.parse_args()


    config_filename = args.config
    device = 'cpu' if args.CPU else None

    # load config
    load_config_flag = False
    try:
        config_dict = json.load(open(config_filename, 'r'))
        cameraMatrix = config_dict['cameraMatrix']
        distCoeffs = config_dict['distCoeffs']
        tag_real_size_in_meter = config_dict['marker_size']
        is_video = config_dict['is_video']!=0
        filename = config_dict['filepath']
        tag_family = config_dict['family']
        codebook_filename  = config_dict['codebook'] if len(config_dict['codebook']) else os.path.join('codebook', tag_family + '_codebook.txt')
        hamming_dist = config_dict['hamming_dist']
        load_config_flag = True
    except:
        print('Cannot load config: %s'% config_filename)  


    # load models
    load_model_flag = False
    try:
        
      model_detector, model_decoder, device, tag_type, grid_size_cand_list = load_deeptag_models(tag_family, device) 
      load_model_flag = True
    except:
        print('Cannot load models.')

    # load marker library
    load_codebook_flag = False
    try:
        
        codebook = load_marker_codebook(codebook_filename, tag_type)
        load_codebook_flag = True
    except:
        print('Cannot load codebook: %s'% codebook_filename)


    # detection
    if load_config_flag and load_codebook_flag and load_model_flag:
        # initialize detection engine
        #print("hi")
        x = Same()
        model_detector.ssd_regressor.stride_features.insert(0, x)
        model_detector = model_detector.half().eval().cuda()
        model_decoder = model_decoder.half().eval().cuda()
        model_detector = torch.jit.load("models/model_detector.ts").eval().half().cuda()
        model_decoder = torch.jit.load("models/model_decoder.ts").eval().half().cuda()
        stag_image_processor = DetectionEngine(model_detector, model_decoder, device, tag_type, grid_size_cand_list, 
                    stg2_iter_num= 2, # 1 or 2
                    min_center_score=0.2, min_corner_score = 0.2, # 0.1 or 0.2 or 0.3
                    batch_size_stg2 = 4, # 1 or 2 or 4
                    hamming_dist= hamming_dist, # 0, 2, 4
                    cameraMatrix = cameraMatrix, distCoeffs=  distCoeffs, codebook = codebook,
                    tag_real_size_in_meter_dict = {-1:tag_real_size_in_meter})


        cap = None 
        if cap is None: cap = cv2.VideoCapture(filename)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 180)
        while True:
            # read video frame or image
            if is_video:
                
                ret, image =cap.read()
                if not ret:
                    print('Cannot read video.')
                    break
            else:
                image = cv2.imread(filename)
                image = cv2.resize(image, (320, 180))
                if image is None:
                    print('Cannot read image.')
                    break

            # detect markers, print timing, visualize poses
            decoded_tags = stag_image_processor.process(image, detect_scale=None)
            pose_topic.set([decoded_tags["tag_id"], decoded_tags["tvecs"], decoded_tags["rvecs"]])
            #stag_image_processor.print_timming()
            #c = stag_image_processor.visualize(is_pause= not is_video)

            # press ESC or q to exit
            #if c == 27 or c == ord('q') or not is_video:
                #break
        

        if cap is not None: cap.release()

               
