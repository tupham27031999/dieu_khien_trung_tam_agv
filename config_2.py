# config.py
import os
import json
import numpy as np
import cv2
from libs_file import remove

def edit_path(input):
    return input.replace("\\", "/")

PATH_PHAN_MEM = edit_path(os.path.dirname(os.path.realpath(__file__)))
PATH_POINTS_DIR = remove.tao_folder(PATH_PHAN_MEM + "/data_input_output/point_lists")
PATH_PATHS_DIR = remove.tao_folder(PATH_PHAN_MEM + "/data_input_output/path_lists")

class AGVConfig_2:
    danh_sach_diem = None
    danh_sach_duong = None
    graph = None

    setup_manager = False