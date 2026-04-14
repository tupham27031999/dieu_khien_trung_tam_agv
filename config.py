# config.py
import os
import json
import numpy as np
import cv2
from libs_file import remove


def get_occupancy_image(log_odds_map=None):
    log_odds = log_odds_map if log_odds_map is not None else np.zeros((100, 100))  # Default to a blank image if no map is provided
    p = 1.0 / (1.0 + np.exp(-log_odds))
    img = np.full_like(log_odds, 128, dtype=np.uint8)
    img[p < 0.1] = 255    # free -> trắng
    img[p > 0.6] = 0      # tường -> đen
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) # Luôn trả về ảnh 3 kênh  


def read_json_file(file_path):
    """
    Đọc dữ liệu từ một file JSON.

    Args:
        file_path (str): Đường dẫn đến file JSON.

    Returns:
        tuple: (data, message)
            - data (dict | list | None): Dữ liệu đã được đọc từ file JSON,
                                          hoặc None nếu có lỗi.
            - message (str): Thông báo thành công hoặc lỗi.
    """
    if not os.path.exists(file_path):
        return None, f"Lỗi: File không tồn tại tại đường dẫn: {os.path.abspath(file_path)}"

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"Lỗi giải mã JSON: {e}"
    except Exception as e:
        return None, f"Lỗi không xác định khi đọc file: {e}"





class AGVConfig:
    
    VERSION = "1.0.0"
    PATH_PHAN_MEM = (os.path.dirname(os.path.realpath(__file__))).replace("\\", "/")
    ten_dieu_de = "AGV Control Panel"
    PATH_SETTING = os.path.join(PATH_PHAN_MEM, "setting", "setting.json")
    data_setting, error = read_json_file(PATH_SETTING)
    ten_danh_sach_diem = data_setting["ten_danh_sach_diem"]
    ten_danh_sach_duong = data_setting["ten_danh_sach_duong"]


    path_logo = PATH_PHAN_MEM + "/static/" + data_setting["ten_logo"]
    path_map = PATH_PHAN_MEM + "/data_input_output/maps/" + data_setting["ten_map"] + "/log_odds.npy"
    path_markers = PATH_PHAN_MEM + "/" + data_setting["path_markers"]
    path_diem_chiem_dung = PATH_PHAN_MEM + "/" + data_setting["path_diem_chiem_dung"]
    path_danh_sach_diem = PATH_PHAN_MEM + "/data_input_output/point_lists/" + ten_danh_sach_diem
    path_danh_sach_duong = PATH_PHAN_MEM + "/data_input_output/path_lists/" + ten_danh_sach_duong
    path_folder_upload = remove.tao_folder(PATH_PHAN_MEM + "/" + data_setting["path_folder_upload"])
    path_folder_dowload = remove.tao_folder(PATH_PHAN_MEM + "/" + data_setting["path_folder_dowload"])
    path_backup = remove.tao_folder(PATH_PHAN_MEM + "/" + data_setting["path_backup"])
    path_download_json = PATH_PHAN_MEM + "/" + data_setting["path_download_json"]

    

    os.makedirs(path_folder_upload, exist_ok=True)
    os.makedirs(path_backup, exist_ok=True)

    # độ phân giải của bản đồ (mm/pixel)
    map_resolution = data_setting["map_resolution"]
    BASE_IP = data_setting["BASE_IP"]

    diem_chiem_dung = {}
    # diem_chiem_dung = {
    #     ("A3", "A2"): [("A5", "A1")], # Khi đi từ A3 sang A2, khóa đường từ A5 -> A1
    #     ("A7", "A8"): [("B5", "B1")], 
    # Tự động nạp dữ liệu từ file nếu có
    if os.path.exists(path_diem_chiem_dung):
        try:
            with open(path_diem_chiem_dung, 'r', encoding='utf-8') as f:
                diem_chiem_dung = json.load(f)
        except: pass

    img = get_occupancy_image(log_odds_map=np.load(path_map))
    # cv2.imwrite("map.png", img)

    danh_sach_diem = {}
    if os.path.exists(path_danh_sach_diem):
        with open(path_danh_sach_diem, 'r', encoding='utf-8') as f:
            danh_sach_diem = json.load(f)
    

    DANH_SACH_AGV = data_setting["DANH_SACH_AGV"]
    thong_tin_hien_thi = "agv1: idle, agv2: idle, agv3: idle, agv4: idle, agv5: idle, agv6: idle, agv7: idle"
    # Cấu trúc nhiều hàng
    # BAN_DO_KE = {
    #     "A": [],
    #     "B": [["B01", "P10"], ["B02", "P10"], ["B03", "P10"], ["B04", "P10"], ["B05", "P11"], ["B06", "P11"], ["B07", "P12"], ["B08", "P12"], ["B09", "P13"], ["B10", "P13"], ["B11", "P14"], ["B12", "P14"]],
    #     "C": [["C01", "P10"], ["C02", "P10"], ["C03", "P10"], ["C04", "P11"], ["C05", "P11"], ["C06", "P12"], ["C07", "P12"], ["C08", "P13"], ["C09", "P13"], ["C10", "P14"], ["C11", "P14"]],
    #     "D": [["D01", "P19"], ["D02", "P19"], ["D03", "P19"], ["D04", "P18"], ["D05", "P17"], ["D06", "P17"], ["D07", "P16"], ["D08", "P16"], ["D09", "P15"], ["D10", "P15"], ["D11", "P15"]],
    #     "E": [["E01", "P19"], ["E02", "P19"], ["E03", "P19"], ["E04", "P18"], ["E05", "P17"], ["E06", "P17"], ["E07", "P16"], ["E08", "P16"], ["E09", "P15"], ["E10", "P15"], ["E11", "P15"]],
    #     "F": [["F01", "P49"], ["F02", "P49"], ["F03", "P49"], ["F04", "P50"], ["F05", "P50"], ["F06", "P51"], ["F07", "P51"], ["F08", "P52"], ["F09", "P52"], ["F10", "P53"], ["F11", "P53"]],
    #     "G": [["G01", "P49"], ["G02", "P49"], ["G03", "P49"], ["G04", "P50"], ["G05", "P50"], ["G06", "P51"], ["G07", "P51"], ["G08", "P52"], ["G09", "P52"], ["G10", "P53"], ["G11", "P53"]],
    #     "H": [["H01", "P44"], ["H02", "P44"], ["H03", "P44"], ["H04", "P45"], ["H05", "P45"], ["H06", "P46"], ["H07", "P46"], ["H08", "P47"], ["H09", "P47"], ["H10", "P48"], ["H11", "P48"]],
    #     "I": [["I01", "P44"], ["I02", "P44"], ["I03", "P44"], ["I04", "P45"], ["I05", "P45"], ["I06", "P46"], ["I07", "P46"], ["I08", "P47"], ["I09", "P47"], ["I10", "P48"], ["I11", "P48"]],
    #     "J": [["J01", "P39"], ["J02", "P39"], ["J03", "P39"], ["J04", "P40"], ["J05", "P40"], ["J06", "P41"], ["J07", "P41"], ["J08", "P42"], ["J09", "P42"], ["J10", "P43"], ["J11", "P43"]],
    #     "tra_hang": [["X01", "X1"], ["X02", "X2"], ["X03", "X3"], ["X04", "X4"]],
    #     "lay_hang": [["X01", "X1"], ["X02", "X2"], ["X03", "X3"], ["X04", "X4"]],
    # }
    CAC_LOAI_KE = data_setting["CAC_LOAI_KE"]
    BAN_DO_KE = {}
    
    # Tự động load BAN_DO_KE từ file markers.json nếu tồn tại
    if os.path.exists(path_markers):
        try:
            with open(path_markers, 'r', encoding='utf-8') as f:
                _markers_data = json.load(f)
                for _m in _markers_data:
                    _group = _m.get("group")
                    _name = _m.get("name")
                    _point = _m.get("diem_lay_hang", "")
                    if _group and _name:
                        if _group not in BAN_DO_KE:
                            BAN_DO_KE[_group] = []
                        BAN_DO_KE[_group].append([_name, _point])
        except Exception as e:
            print(f"Lỗi khi load BAN_DO_KE từ file: {e}")
    print(BAN_DO_KE)
    # các giá hàng có thể chọn sẽ là các key của BAN_DO_KE
    cac_gia_hang = {}
    for key in BAN_DO_KE.keys():
        cac_gia_hang[key] = [item[0] for item in BAN_DO_KE[key]]  # Lấy tên giá hàng từ cấu trúc BAN_DO_KE
    # print("CÁC GIÁ HÀNG CÓ THỂ CHỌN:", cac_gia_hang)
    # {'A': [], 'B': ['B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08', 'B09', 'B10', 'B11', 'B12'], 'C': [
    lua_chon_yeu_cau = {"chon_gia_hang": {"ten_hien_thi": "Chọn giá hàng", "loai": "select", "value": "None", "options": CAC_LOAI_KE},
                        "di_chuyen_khong_hang": {"ten_hien_thi": "Di chuyển không hàng", "loai": "on/off", "value": "off", "options": None},
                        "che_do_dieu_khien_truc_tiep": {"ten_hien_thi": "Chế độ điều khiển trực tiếp", "loai": "on/off", "value": "off", "options": None},}

    # Di chuyển AGV_STATES lên trên để thong_tin_da_chon có thể tham chiếu giá trị mặc định
    AGV_STATES = {
        agv: {
            "vi_tri_hien_tai": "", 
            "diem_tiep_theo": "", 
            "dich_den": "", 
            "trang_thai_agv_gui": "idle", 
            "trang_thai_gui_agv": "idle", 
            "message": "Khởi tạo", 
            "danh_sach_duong_di": [], 
            "danh_sach_toa_do_duong_di": [], 
            "paths": [], 
            "stop": False, 
            "toa_do": {"x": 0, "y": 0}, 
            "goc_agv": 0, 
            "di_chuyen_khong_hang": False, 
            "che_do_dieu_khien_truc_tiep": False, # Giá trị mặc định thực tế
            "da_den_dich": False
        } for agv in DANH_SACH_AGV
    }

    # thông tin đã chọn theo từng agv
    thong_tin_da_chon = {}
    for agv in DANH_SACH_AGV:
        thong_tin_da_chon[agv] = {key: value["value"] for key, value in lua_chon_yeu_cau.items()}
        thong_tin_da_chon[agv]["danh_sach_ke_da_chon"] = [] # Thêm biến lưu danh sách các giá (B01, C02...) đã chọn
        
        # Cập nhật mặc định theo biến che_do_dieu_khien_truc_tiep của AGV_STATES tương ứng
        # Nếu AGV_STATES là False thì hiển thị "off", nếu True thì hiển thị "on"
        thong_tin_da_chon[agv]["che_do_dieu_khien_truc_tiep"] = "on" if AGV_STATES[agv]["che_do_dieu_khien_truc_tiep"] else "off"

    trang_thai_gui = {agv: False for agv in DANH_SACH_AGV} # Biến kiểm soát việc đã gửi lệnh hay chưa
    trang_thai_hoan_thanh = {agv: False for agv in DANH_SACH_AGV} # Biến giả lập tín hiệu hoàn thành
    
    # Biến lưu chỉ số (index) hiện tại trong danh sách đã chọn của từng AGV
    chi_so_hang_hien_tai = {agv: 0 for agv in DANH_SACH_AGV}
    # Biến đặc biệt lưu giá trị hàng hiện tại (ví dụ: "B01") dựa trên chỉ số index
    gia_tri_hang_hien_tai = {agv: "" for agv in DANH_SACH_AGV}
    # đích đến sẽ gửi cho agv
    dich_den_gui_agv = {agv: "" for agv in DANH_SACH_AGV}

    # Cấu hình hiển thị bản đồ
    hien_thi_diem = True  # Mặc định hiển thị điểm
    hien_thi_duong = True # Mặc định hiển thị đường

    kich_thuoc_agv = data_setting["kich_thuoc_agv"] # pixel - để vẽ agv trên web
    agv_color = {}
    # không dùng màu đen và trắng
    # chuyển [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0], [255, 0, 255], [0, 255, 255], [26, 127, 239]] sang dạng tuple để dễ sử dụng với OpenCV
    color_list = [tuple(color) for color in data_setting["color_list"]]
    for agv in DANH_SACH_AGV:
        agv_color[agv] = color_list[DANH_SACH_AGV.index(agv)]
    

    # tạo 1 danh sách để lưu thông tin IP kết nối từ AGV và thời gian chúng chưa kết nối lại, 
    # để nếu quá thời gian cho phép thì sẽ xóa chúng khỏi danh sách
    # danh_sach_ip_ket_noi = {"thong_tin_1": {"ip": "10.47.240.18:5001", "thoi_gian_chua_ket_noi_lai": 2},
    #                         "thong_tin_2": {"ip": "10.47.240.19:5002", "thoi_gian_chua_ket_noi_lai": 2},
    #                         "thong_tin_3": {"ip": "10.47.240.20:5003", "thoi_gian_chua_ket_noi_lai": 2}} # Biến lưu IP kết nối từ AGV gửi đến

    # Cấu hình danh sách endpoint để Server chủ động gọi AGV
    # Chuyển từ app.py sang đây để quản lý tập trung
    # Sửa lỗi NameError: name 'BASE_IP' is not defined bằng cách dùng vòng lặp tường minh (Class Scope safety)
    AGV_ENDPOINTS = {}
    _ips = data_setting.get("BASE_IP", [])
    for i in range(len(_ips)):
        AGV_ENDPOINTS[f"agv{i+1}"] = f"http://{_ips[i]}:{5001+i}/PC_sent_AGV"
    print("AGV_ENDPOINTS", AGV_ENDPOINTS)

    danh_sach_ip_ket_noi = {} # Biến lưu IP kết nối: {"agv1": {"address": "ip:port", "last_seen": timestamp}}
    