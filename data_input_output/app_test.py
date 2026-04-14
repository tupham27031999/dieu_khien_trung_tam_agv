import os
import cv2
import threading
import time
import random
import requests
import shutil
from flask import Flask, render_template, url_for, jsonify, request, Response, send_from_directory
from config import AGVConfig
import numpy as np
import config
from datetime import datetime
import json
import process

PATH_DATA_IN_OUT = config.PATH_PHAN_MEM + "/data_input_output"


# Khởi tạo ứng dụng Flask
# template_folder: nơi chứa file html (templates)
# static_folder: nơi chứa css, js, images (static)
app = Flask(__name__)

# Nạp cấu hình (nếu cần dùng app.config['KEY'])
app.config.from_object(AGVConfig)


@app.route('/')
def home():
    """
    Route trang chủ. Render home.html và truyền các tham số từ Config.
    """
    return render_template('home.html', config=AGVConfig)


@app.route('/api/map_image')
def map_image():
    """
    API trả về ảnh bản đồ từ bộ nhớ.
    Sử dụng tham số source=mapping để lấy bản đồ đang quét, ngược lại lấy bản đồ vận hành.
    Không cần lưu file ra đĩa.
    """
    source = request.args.get('source', 'home')
    img_to_send = AGVConfig.img_mapping if source == 'mapping' else AGVConfig.img
    
    is_success, buffer = cv2.imencode(".png", img_to_send)
    if is_success:
        response = Response(buffer.tobytes(), mimetype='image/png')
        # Ngăn chặn cache để ảnh luôn được cập nhật mới nhất
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    return "Error encoding image", 500

@app.route('/api/map_tile/<int:level>/<int:x>/<int:y>/<int:size>')
def map_tile(level, x, y, size):
    """
    API trả về một ô (tile) cụ thể của bản đồ.
    """
    h, w = AGVConfig.img.shape[:2]
    
    # Tính toán tỷ lệ dựa trên level (OpenSeadragon Pyramid)
    # max_level cho 5000px là ~13. Nếu level thấp hơn, ta cần lấy vùng lớn hơn và resize lại.
    max_level = int(np.ceil(np.log2(max(w, h))))
    factor = 2 ** (max_level - level)
    
    x1, y1 = x * size * factor, y * size * factor
    x2, y2 = x1 + size * factor, y1 + size * factor

    # Cắt vùng ảnh tương ứng (xử lý tràn biên)
    tile = AGVConfig.img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    
    # Nếu vùng cắt không đủ kích thước (ô ở rìa), ta có thể giữ nguyên hoặc pad 
    if factor > 1 and tile.size > 0:
        tile = cv2.resize(tile, (size, size), interpolation=cv2.INTER_NEAREST)

    # Sử dụng JPEG chất lượng 80 để tối ưu tốc độ truyền tải
    is_success, buffer = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if is_success:
        response = Response(buffer.tobytes(), mimetype='image/jpeg')
        # Cực kỳ quan trọng: Ngăn chặn tuyệt đối việc lưu cache ảnh tile
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    return "Tile error", 404

@app.route('/api/map_region')
def map_region():
    """
    API trả về một vùng bản đồ hình chữ nhật quanh tọa độ (x, y).
    Sử dụng kích thước từ AGVConfig.kich_thuoc_mapping_update.
    """
    x = int(request.args.get('x', 0))
    y = int(request.args.get('y', 0))
    w_up, h_up = AGVConfig.kich_thuoc_mapping_update
    
    # Tính toán tọa độ cắt (xử lý tràn biên)
    x1 = max(0, x - w_up // 2)
    y1 = max(0, y - h_up // 2)
    x2 = min(AGVConfig.w_pixel, x1 + w_up)
    y2 = min(AGVConfig.h_pixel, y1 + h_up)
    
    # Cắt vùng ảnh từ bản đồ gốc trong bộ nhớ
    crop = AGVConfig.img_mapping[y1:y2, x1:x2]
    
    is_success, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 50])
    if is_success:
        response = Response(buffer.tobytes(), mimetype='image/jpeg')
        return response
    return "Crop error", 404

@app.route('/api/status')
def get_status():
    """
    API trả về trạng thái hiện tại của AGV (Pin, trạng thái chạy, v.v.)
    """
    # Cập nhật tọa độ pixel của các vùng chân xe theo vị trí AGV hiện tại trước khi gửi đi
    AGVConfig.update_pixel_exclusion_zones()
    return jsonify({
        "phan_tram_pin": AGVConfig.phan_tram_pin,
        "run_state": AGVConfig.run_state,
        "motor_state": AGVConfig.motor_state,
        "toa_do_agv_pixel": AGVConfig.toa_do_agv_pixel,
        "huong_agv_do_img": AGVConfig.huong_agv_do_img,
        "danh_sach_duong_di": AGVConfig.danh_sach_duong_di,
        "kich_thuoc_agv": AGVConfig.kich_thuoc_agv,
        # Sử dụng slicing [::skip] để giảm số điểm gửi lên Web nhanh chóng
        "danh_sach_diem_lidar": AGVConfig.danh_sach_diem_lidar_icp[::AGVConfig.lidar_display_skip, :2].tolist() if (AGVConfig.an_hien_diem_lidar_icp or AGVConfig.che_do_tao_ban_do) else [],
        "danh_sach_diem_vat_can": AGVConfig.danh_sach_diem_vat_can if AGVConfig.an_hien_diem_lidar_icp else [],
        "vung_loai_bo_mm": AGVConfig.vung_loai_bo_x1y1x2y2,
        "vung_loai_bo_pixel": AGVConfig.vung_loai_bo_x1y1x2y2_pixel,
        "hien_thi_chan_xe": AGVConfig.hien_thi_chan_xe,
        "lidar1": AGVConfig.lidar1,
        "lidar2": AGVConfig.lidar2,
        "esp32": AGVConfig.esp32,
        "driver_motor": AGVConfig.driver_motor,
        "pin": AGVConfig.pin,
        "che_do_tao_ban_do": AGVConfig.che_do_tao_ban_do,
        "tao_ban_do_moi": AGVConfig.tao_ban_do_moi,
        "chinh_sua_ban_do": AGVConfig.chinh_sua_ban_do,
        "trang_thai_tam_dung_tao_ban_do": AGVConfig.trang_thai_tam_dung_tao_ban_do,
        "w_pixel": AGVConfig.w_pixel,
        "h_pixel": AGVConfig.h_pixel,
        "update_all_point_in_map": AGVConfig.update_all_point_in_map,
        "tam_thoi_reset_vung_loai_bo": AGVConfig.tam_thoi_reset_vung_loai_bo,
        "cap_nhat_ban_do_1_lan_web": AGVConfig.cap_nhat_ban_do_1_lan_web,
        "thoi_gian_cap_nhat": AGVConfig.thoi_gian_cap_nhat,
        "dieu_khien_agv": AGVConfig.dieu_khien_agv,
        "sac_pin": AGVConfig.sac_pin,
        "tat_phan_mem": AGVConfig.tat_phan_mem,
        "server_shutdown_imminent": AGVConfig.server_shutdown_imminent, # NEW: Báo hiệu server sắp tắt
        "is_syncing": AGVConfig.is_syncing # NEW: Gửi trạng thái đồng bộ về Web
    })

@app.route('/api/update_manual_pos', methods=['POST'])
def update_manual_pos():
    """
    API cập nhật cấu hình vị trí thủ công (toa_do, huong, flags)
    """
    data = request.json
    for key in ['toa_do', 'huong', 'update_tam_thoi', 'update']:
        if key in data:
            # Cập nhật vào dictionary trong Config
            AGVConfig.cap_nhat_vi_tri_agv[key] = data[key]
            # print(key, data[key])
            # test
            if AGVConfig.cap_nhat_vi_tri_agv["update"] == True:
                AGVConfig.cap_nhat_vi_tri_agv["update"] = False
                AGVConfig.cap_nhat_vi_tri_agv["update_tam_thoi"] = False
                AGVConfig.toa_do_agv_pixel = AGVConfig.cap_nhat_vi_tri_agv["toa_do"]
                AGVConfig.huong_agv_do_img = AGVConfig.cap_nhat_vi_tri_agv["huong"]

    return jsonify({"status": "success", "data": AGVConfig.cap_nhat_vi_tri_agv})

@app.route('/api/loai_bo_chan_xe/save', methods=['POST'])
def save_loai_bo_chan_xe():
    """API lưu vùng chân xe đang lấy mẫu vào file JSON"""
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"status": "error", "message": "Tên file không hợp lệ"}), 400
    
    # Gọi hàm thực hiện lưu file JSON từ vung_loai_bo_x1y1x2y2
    AGVConfig.save_loai_bo_to_file(name)
    # Trả về danh sách mới để cập nhật UI không cần reload
    return jsonify({"status": "success", "danh_sach": AGVConfig.danh_sach_vung_loai_bo})

@app.route('/api/loai_bo_chan_xe/load', methods=['POST'])
def load_loai_bo_chan_xe():
    """API tải vùng chân xe từ file JSON đã chọn"""
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"status": "error", "message": "Chưa chọn file"}), 400
    print("Loading exclusion zone from file:", data)
    AGVConfig.load_loai_bo(name)
    AGVConfig.loai_bo_coc_xe["ten_vung_loai_bo"] = name
    AGVConfig.loai_bo_coc_xe["update"] = 1
    AGVConfig.save_to_file()
    return jsonify({"status": "success", "vung_moi": AGVConfig.vung_loai_bo_x1y1x2y2})

@app.route('/api/toggle_lidar_view', methods=['POST'])
def toggle_lidar_view():
    """API bật/tắt hiển thị điểm Lidar trên bản đồ"""
    data = request.json
    AGVConfig.an_hien_diem_lidar_icp = data.get('state', False)
    return jsonify({"status": "success", "state": AGVConfig.an_hien_diem_lidar_icp})

@app.route('/api/map/toggle_create_mode', methods=['POST'])
def toggle_create_map_mode():
    data = request.json
    AGVConfig.che_do_tao_ban_do = data.get('state', False)
    return jsonify({"status": "success", "state": AGVConfig.che_do_tao_ban_do})

@app.route('/api/map/toggle_pause', methods=['POST'])
def toggle_pause_map():
    AGVConfig.trang_thai_tam_dung_tao_ban_do = not AGVConfig.trang_thai_tam_dung_tao_ban_do
    return jsonify({"status": "success", "paused": AGVConfig.trang_thai_tam_dung_tao_ban_do})

@app.route('/api/map/save', methods=['POST'])
def save_new_map_api():
    AGVConfig.lenh_luu_ban_do = 1
    return jsonify({"status": "success"})

@app.route('/api/loai_bo_chan_xe/toggle_sampling', methods=['POST'])
def toggle_lidar_sampling():
    """API bật/tắt chế độ lấy mẫu chân xe"""
    data = request.json
    AGVConfig.loai_bo_coc_xe["che_do_lay_mau"] = 1 if data.get('state') else 0
    return jsonify({"status": "success", "state": AGVConfig.loai_bo_coc_xe["che_do_lay_mau"]})

@app.route('/api/loai_bo_chan_xe/update_mm', methods=['POST'])
def update_lidar_mm():
    """API cập nhật tọa độ mm vùng loại bỏ từ web"""
    data = request.json
    new_zones = data.get('zones')
    if new_zones:
        AGVConfig.vung_loai_bo_x1y1x2y2 = new_zones
        AGVConfig.update_pixel_exclusion_zones()
        print("Updated exclusion zones (mm):", AGVConfig.vung_loai_bo_x1y1x2y2)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

@app.route('/api/toggle_check_pos', methods=['POST'])
def toggle_check_pos():
    """API bật/tắt chế độ kiểm tra vị trí xe"""
    data = request.json
    AGVConfig.kiem_tra_vi_tri_xe = data.get('state', False)
    return jsonify({"status": "success", "state": AGVConfig.kiem_tra_vi_tri_xe})

@app.route('/api/xoa_vung_ban_do/add', methods=['POST'])
def add_delete_area():
    """API thêm vùng hình chữ nhật vào danh sách xóa"""
    data = request.json
    area = data.get('area') # [x1, y1, x2, y2]
    if area:
        AGVConfig.xoa_vung_ban_do["vung_xoa"].append(area)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

@app.route('/api/xoa_vung_ban_do/clear', methods=['POST'])
def clear_delete_areas():
    AGVConfig.xoa_vung_ban_do["vung_xoa"] = []
    return jsonify({"status": "success"})

@app.route('/api/xoa_vung_ban_do/update', methods=['POST'])
def update_delete_area():
    AGVConfig.xoa_vung_ban_do["update"] = 1
    return jsonify({"status": "success"})

@app.route('/api/update_config', methods=['POST'])
def update_config():
    """
    API để cập nhật các giá trị cấu hình từ giao diện web.
    """
    data = request.json
    key = data.get('key')
    value = data.get('value')

    if hasattr(AGVConfig, key):
        # Chuyển đổi kiểu dữ liệu nếu cần (ví dụ boolean)
        if key in ['motor_state', 'tam_thoi_reset_vung_loai_bo', 'cap_nhat_ban_do_1_lan_web', 'sac_pin', 'tat_phan_mem']:
            value = bool(value)
        setattr(AGVConfig, key, value)

        # Logic reset tạm thời vùng loại bỏ chân xe
        if key == 'tam_thoi_reset_vung_loai_bo':
            if AGVConfig.tam_thoi_reset_vung_loai_bo:
                AGVConfig.vung_loai_bo_x1y1x2y2 = []
                AGVConfig.vung_loai_bo_x1y1x2y2_pixel = []
            else:
                # Load lại từ file đang chọn trong cấu hình
                AGVConfig.load_loai_bo(AGVConfig.loai_bo_coc_xe.get("ten_vung_loai_bo"))

        # Nếu thay đổi bản đồ, nạp lại ảnh vào bộ nhớ
        if key == 'ten_ban_do':
            AGVConfig.reload_map()

        # Nếu thay đổi danh sách điểm, nạp dữ liệu từ file tương ứng
        if key == 'ten_danh_sach_diem':
            AGVConfig.load_points(value)

        # Nếu thay đổi danh sách đường, nạp dữ liệu từ file tương ứng
        if key == 'ten_danh_sach_duong':
            AGVConfig.load_paths(value)

        # Lưu cấu hình vào file nếu là các key cần ghi nhớ (persistence)
        if key in ['ten_ban_do', 'ten_danh_sach_diem', 'ten_danh_sach_duong', 'van_toc_tien_max', 'van_toc_re_max']:
            AGVConfig.save_to_file()

        return jsonify({
            "status": "success", 
            "new_value": getattr(AGVConfig, key),
            "danh_sach_diem": AGVConfig.danh_sach_diem if key == 'ten_danh_sach_diem' else None,
            "danh_sach_duong": AGVConfig.danh_sach_duong if key == 'ten_danh_sach_duong' else None
        })
    
    return jsonify({"status": "error", "message": "Key not found"}), 400

@app.route('/api/save_points', methods=['POST'])
def save_points():
    """API lưu danh sách điểm tạm thời thành file json"""
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"status": "error", "message": "Tên không hợp lệ"}), 400
    
    try:
        AGVConfig.save_points_to_file(name)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/save_paths', methods=['POST'])
def save_paths():
    """API lưu danh sách đường tạm thời thành file json"""
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"status": "error", "message": "Tên không hợp lệ"}), 400
    try:
        AGVConfig.save_paths_to_file(name)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/add_path_temp', methods=['POST'])
def add_path_temp():
    """API lưu đường mới vào danh sách tạm thời"""
    data = request.json
    name = data.get('name')
    nodes = data.get('nodes') # [P1, P2]
    if name and nodes:
        AGVConfig.danh_sach_duong[name] = [nodes, "none"]
        print("đã thêm đường vào danh sách tạm thời: AGVConfig.danh_sach_duong")
        return jsonify({
            "status": "success", 
            "data": AGVConfig.danh_sach_duong,
            "new_path": AGVConfig.danh_sach_duong[name]
        })
    return jsonify({"status": "error"}), 400

@app.route('/api/delete_path_temp', methods=['POST'])
def delete_path_temp():
    """API xóa một đường khỏi danh sách tạm thời"""
    data = request.json
    name = data.get('name')
    if name in AGVConfig.danh_sach_duong:
        del AGVConfig.danh_sach_duong[name]
        print("đã xóa đường khỏi danh sách tạm thời: AGVConfig.danh_sach_duong")
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Path not found"}), 400

@app.route('/api/add_point_temp', methods=['POST'])
def add_point_temp():
    """API lưu điểm mới vào danh sách tạm thời trong config"""
    data = request.json
    name = data.get('name')
    info = data.get('info') # [x, y, type, heading]
    if name and info:
        AGVConfig.danh_sach_diem[name] = info
        print("đã thêm điểm vào danh sách tạm thời: AGVConfig.danh_sach_diem")
        return jsonify({"status": "success", "data": AGVConfig.danh_sach_diem})
    return jsonify({"status": "error"}), 400

@app.route('/api/delete_point_temp', methods=['POST'])
def delete_point_temp():
    """API xóa một điểm khỏi danh sách tạm thời"""
    data = request.json
    name = data.get('name')
    if name in AGVConfig.danh_sach_diem:
        del AGVConfig.danh_sach_diem[name]
        
        # Tự động xóa các đường (paths) có chứa điểm này
        paths_to_delete = [p_name for p_name, p_info in AGVConfig.danh_sach_duong.items() if name in p_info[0]]
        for p_name in paths_to_delete:
            del AGVConfig.danh_sach_duong[p_name]
            print(f"Đã xóa đường {p_name} do chứa điểm {name} bị xóa")

        return jsonify({"status": "success", "danh_sach_duong": AGVConfig.danh_sach_duong})
    return jsonify({"status": "error", "message": "Point not found"}), 400

@app.route('/api/manual_control', methods=['POST'])
def manual_control():
    """API nhận lệnh điều khiển thủ công (tiến, lùi, trái, phải)"""
    data = request.json
    # Cập nhật trạng thái vào Config
    for key in ['dieu_khien_thu_cong', 'tien', 'lui', 'trai', 'phai', 'ha_xe', 'nang_xe']:
        if key in data:
            config.AGVConfig.dieu_khien_agv[key] = data[key]
    
    config.AGVConfig.last_manual_command_time = time.time() # Cập nhật thời gian nhận lệnh cuối cùng
    
    # Debug log (tùy chọn)
    # print("Manual Control State:", config.AGVConfig.dieu_khien_agv)
    
    return jsonify({"status": "success", "data": config.AGVConfig.dieu_khien_agv})

def log_communication(log_type, timestamp_str, signal_value):
    """
    Ghi log giao tiếp vào file.
    log_type: "nhan" hoặc "gui"
    timestamp_str: Thời gian dạng string (YYYY-MM-DD HH:MM:SS)
    signal_value: Giá trị tín hiệu (có thể là string hoặc dict/list)
    """
    try:
        now = time.localtime()
        date_hour_str = time.strftime("%Y-%m-%d_%H", now)
        filename = f"log_{date_hour_str}.txt"
        filepath = os.path.join(config.path_folder_log_giao_tiep, filename)

        # Chuyển đổi signal_value thành chuỗi JSON nếu nó là dict hoặc list
        if isinstance(signal_value, (dict, list)):
            log_content = json.dumps(signal_value, ensure_ascii=False)
        else:
            log_content = str(signal_value)

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"{timestamp_str}\t{log_type}\t{log_content}\n")
    except Exception as e:
        print(f"Error writing to log file: {e}")


@app.route('/PC_sent_AGV', methods=['POST'])
def pc_sent_agv_endpoint():
    data = request.get_json()
    if data:
        tin_hieu_nhan = data
        # cập nhật các thông tin cần thiết'
        AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["dich_den"]             = tin_hieu_nhan[AGVConfig.name_agv]["dich_den"]
        AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["trang_thai_gui_agv"]   = tin_hieu_nhan[AGVConfig.name_agv]["trang_thai_gui_agv"]
        AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["paths"]                = tin_hieu_nhan[AGVConfig.name_agv]["paths"]
        AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["stop"]                 = tin_hieu_nhan[AGVConfig.name_agv]["stop"]
        AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["di_chuyen_khong_hang"] = tin_hieu_nhan[AGVConfig.name_agv]["di_chuyen_khong_hang"]
        thoi_gian_nhan_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # các giá trị gửi đi cho dktt
        vi_tri_hien_tai = AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["vi_tri_hien_tai"]
        diem_tiep_theo = AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["diem_tiep_theo"]
        trang_thai_agv_gui = AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["trang_thai_agv_gui"]
        message_agv = AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["message"]
        danh_sach_duong_di = AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["danh_sach_duong_di"]
        da_den_dich = AGVConfig.tin_hieu_nhan[AGVConfig.name_agv]["da_den_dich"]

        if len(AGVConfig.toa_do_agv_pixel) == 0:
            toa_do_x = -1
            toa_do_y = -1
        else:
            toa_do_x = AGVConfig.toa_do_agv_pixel[0]
            toa_do_y = AGVConfig.toa_do_agv_pixel[1]

        tin_hieu_gui = {AGVConfig.name_agv: {"vi_tri_hien_tai": vi_tri_hien_tai, 
                                            "diem_tiep_theo": diem_tiep_theo,
                                            'trang_thai_agv_gui': trang_thai_agv_gui, 
                                            "message": message_agv,
                                            "danh_sach_duong_di": danh_sach_duong_di,
                                            "toa_do": {"x": toa_do_x, "y": toa_do_y},
                                            "da_den_dich": da_den_dich
                                            }
                        }

        log_communication("nhan", thoi_gian_nhan_str, tin_hieu_nhan)
        log_communication("gui", thoi_gian_nhan_str, tin_hieu_gui)
        return jsonify({"status": "success", "data": tin_hieu_gui}), 200
    return jsonify({"status": "error", "message": "Invalid signal data. Expecting {'signal': 'your_string'}."}), 400


def tat_phan_mem():
    if AGVConfig.tat_phan_mem == True:
        # các hàm khác sẽ thêm vào đây sau
        AGVConfig.server_shutdown_imminent = True # Báo hiệu cho client rằng server sắp tắt
        return True
    return False



@app.route('/api/download_update/<path:filepath>')
def download_update_file(filepath):
    """
    API cho phép Master Server tải file từ AGV này về.
    File sẽ được lấy trực tiếp từ đường dẫn tương đối trong thư mục phần mềm.
    """
    return send_from_directory(config.PATH_PHAN_MEM, filepath)

@app.route('/api/sync_from_master', methods=['POST'])
def sync_from_master():
    """
    Endpoint tiếp nhận lệnh đồng bộ từ Server Master.
    AGV sẽ chủ động lấy danh sách và tải file về.
    """
    data = request.json
    # Server gửi IP của nó tới AGV
    master_ip = data.get('master_ip')
    master_port = data.get('master_port', 5000)
    AGVConfig.cap_nhat_tu_server = True
    
    if not master_ip:
        return jsonify({'status': 'error', 'message': 'Thiếu địa chỉ IP của Master Server'}), 400

    master_url = f"http://{master_ip}:{master_port}"

    

    try:
        AGVConfig.is_syncing = True # Bật cờ báo hiệu bắt đầu đồng bộ
        
        # Tạo thư mục backup với timestamp cho lần đồng bộ này
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_backup_dir = os.path.join(config.path_backup, timestamp)
        # 1. Gọi tới Server để lấy danh sách file cần đồng bộ (manifest)
        resp = requests.get(f"{master_url}/api/get_sync_manifest", timeout=5)
        if resp.status_code != 200:
            return jsonify({'status': 'error', 'message': 'Không thể lấy danh sách cập nhật từ Server'}), 500
        
        manifest_data = resp.json()
        files_to_sync = manifest_data.get('files', [])
        
        backup_manifest_entries = [] # Để lưu thông tin vào backup_manifest.json
        updated_files = []
        for item in files_to_sync:
            filename = item['name']
            target_rel_path = item['target'].lstrip('/')
            download_url = f"{master_url}/api/download_update/{target_rel_path.lstrip('/')}"
            
            # 2. Tải từng file từ Server
            file_resp = requests.get(download_url, timeout=15)
            if file_resp.status_code == 200:
                # Đường dẫn tuyệt đối trên AGV
                final_path = os.path.join(config.PATH_PHAN_MEM, target_rel_path)
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                
                # Backup file cũ nếu tồn tại trước khi ghi đè
                if os.path.exists(final_path):
                    os.makedirs(current_backup_dir, exist_ok=True)
                    backup_file_path = os.path.join(current_backup_dir, filename)
                    shutil.copy2(final_path, backup_file_path)
                    backup_manifest_entries.append({
                        "filename": filename,
                        "original_target_rel_path": target_rel_path
                    })
                
                # 3. Ghi đè file vào hệ thống cục bộ
                with open(final_path, 'wb') as f:
                    f.write(file_resp.content)
                updated_files.append(filename)
        
        # Lưu backup_manifest.json nếu có file được backup
        if backup_manifest_entries:
            os.makedirs(current_backup_dir, exist_ok=True)
            with open(os.path.join(current_backup_dir, "backup_manifest.json"), 'w', encoding='utf-8') as f:
                json.dump({"timestamp": timestamp, "files_backed_up": backup_manifest_entries}, f, indent=4, ensure_ascii=False)

        # 4. Hậu xử lý: Nếu có cập nhật bản đồ (log_odds.npy), nạp lại vào bộ nhớ
        if any('log_odds.npy' in f for f in updated_files):
            AGVConfig.reload_map()
            print("Đã nạp lại bản đồ mới sau khi đồng bộ.")

        return jsonify({
            'status': 'success', 
            'message': f'Đã đồng bộ thành công {len(updated_files)} file',
            'details': updated_files
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        AGVConfig.is_syncing = False # Tắt cờ báo hiệu dù thành công hay thất bại

@app.route('/api/list_backups')
def list_backups():
    """
    API liệt kê tất cả các bản sao lưu có sẵn trong thư mục config.path_backup.
    Mỗi bản sao lưu là một thư mục có tên là timestamp.
    """
    backups = []
    if not os.path.exists(config.path_backup):
        return jsonify(backups)

    for entry in os.listdir(config.path_backup):
        backup_path = os.path.join(config.path_backup, entry)
        if os.path.isdir(backup_path):
            manifest_path = os.path.join(backup_path, "backup_manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    backups.append({
                        "timestamp": manifest.get("timestamp", entry),
                        "files_backed_up": manifest.get("files_backed_up", [])
                    })
                except json.JSONDecodeError:
                    # Bỏ qua các thư mục không có manifest hợp lệ
                    pass
            else:
                # Nếu không có manifest, chỉ liệt kê các file có trong thư mục backup
                files_in_backup = [f for f in os.listdir(backup_path) if os.path.isfile(os.path.join(backup_path, f))]
                backups.append({
                    "timestamp": entry,
                    "files_backed_up": [{"filename": f, "original_target_rel_path": f} for f in files_in_backup]
                })
    
    # Sắp xếp theo timestamp mới nhất lên đầu
    backups.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(backups)

@app.route('/api/restore_backup', methods=['POST'])
def restore_backup():
    """
    API khôi phục một file cụ thể từ bản sao lưu.
    """
    data = request.json
    timestamp = data.get('timestamp')
    filename = data.get('filename')
    original_target_rel_path = data.get('original_target_rel_path')

    if not all([timestamp, filename, original_target_rel_path]):
        return jsonify({'status': 'error', 'message': 'Thiếu thông tin khôi phục'}), 400

    source_path = os.path.join(config.path_backup, timestamp, filename)
    destination_path = os.path.join(config.PATH_PHAN_MEM, original_target_rel_path)

    if not os.path.exists(source_path):
        return jsonify({'status': 'error', 'message': f'File backup không tồn tại: {source_path}'}), 404

    try:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copy2(source_path, destination_path)
        # Nếu là file bản đồ, cần nạp lại
        if filename == 'log_odds.npy':
            AGVConfig.reload_map()
        return jsonify({'status': 'success', 'message': f'Đã khôi phục {filename} từ bản sao lưu {timestamp}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Lỗi khi khôi phục file: {str(e)}'}), 500





_last_che_do_tao_ban_do = False
t = time.time()
time_tat_phan_mem = 0
def icp_simulation_loop(handler):
    """
    Luồng mô phỏng xử lý ICP. 
    Vẽ trực tiếp lên AGVConfig.img_mapping để kiểm tra việc cập nhật bản đồ trên Web.
    """
    global _last_che_do_tao_ban_do, time_tat_phan_mem, t
    
    while True:
        # Kiểm tra điều kiện tắt phần mềm và Web Server
        if tat_phan_mem():
            if time_tat_phan_mem == 0:
                time_tat_phan_mem = time.time()
            else:
                if time.time() - time_tat_phan_mem > 4:
                    print("Yêu cầu tắt hệ thống nhận được. Đang đóng Web Server và các tiến trình...")
                    os._exit(0) # Thoát toàn bộ chương trình ngay lập tức
        # print(f"ICP Simulation Loop iteration {t}", time.time() - t) # laptop - không cập nhật map - 0.03, laptop - cập nhật map - 0.06, PC công nghiệp - không cập nhật 0.007s - cập nhật map 0.05s
        # t= time.time()
        handler.loop()
        # # Watchdog cho điều khiển thủ công (An toàn mạng)
        # if AGVConfig.dieu_khien_agv.get("dieu_khien_thu_cong"):
        #     # Nếu quá 0.5 giây không nhận được "Heartbeat" từ Client, tự động dừng xe
        #     if time.time() - AGVConfig.last_manual_command_time > 0.5:
        #         AGVConfig.dieu_khien_agv['tien'] = 0
        #         AGVConfig.dieu_khien_agv['lui'] = 0
        #         AGVConfig.dieu_khien_agv['trai'] = 0
        #         AGVConfig.dieu_khien_agv['phai'] = 0

        # if AGVConfig.che_do_tao_ban_do:
        #     # Khởi tạo bản đồ mapping khi bắt đầu phiên quét mới (Transition False -> True)
        #     if not _last_che_do_tao_ban_do:
        #         h, w = AGVConfig.img.shape[:2]
        #         if AGVConfig.tao_ban_do_moi:
        #             # Tạo bản đồ mới hoàn toàn với màu xám
        #             AGVConfig.img_mapping = np.ones((h, w, 3), dtype=np.uint8) * 128
        #         else:
        #             # Chỉnh sửa: copy từ bản đồ tĩnh hiện tại
        #             AGVConfig.img_mapping = AGVConfig.img.copy()
        #     print("Simulating ICP update... Mapping mode active", AGVConfig.trang_thai_tam_dung_tao_ban_do)
        #     if not AGVConfig.trang_thai_tam_dung_tao_ban_do:
        #         # print("Simulating ICP update... Running")
        #         h, w = AGVConfig.img_mapping.shape[:2]
            

        #         # thay đổi tọa độ AGVConfig.toa_do_agv_pixel mô phỏng di chuyển ngẫu nhiên trong phạm vi 100 pixel quanh điểm [1700, 2449] để kiểm tra cập nhật bản đồ
        #         AGVConfig.toa_do_agv_pixel[0] = 1700 + random.randint(-200, 200)
        #         AGVConfig.toa_do_agv_pixel[1] = 2449 + random.randint(-200, 200)

        #         # Lấy vị trí AGV hiện tại làm tâm điểm quét
        #         x, y = AGVConfig.toa_do_agv_pixel

        #         # Mô phỏng vẽ vùng trống (màu trắng) xung quanh xe
        #         for _ in range(5):
        #             rx = x + random.randint(-150, 150)
        #             ry = y + random.randint(-150, 150)
        #             if 0 <= rx < w and 0 <= ry < h:
        #                 cv2.circle(AGVConfig.img_mapping, (rx, ry), 15, (255, 0, 255), -1)
                
        #         # Thỉnh thoảng vẽ một "bức tường" (màu đen) để kiểm tra độ nét
        #         if random.random() > 0.8:
        #             cv2.rectangle(AGVConfig.img, (x+60, y+60), (x+70, y+100), (0, 0, 0), -1)
        # else:
        #     # Khi không ở chế độ mapping, đồng bộ img_mapping với img hiện tại để tab Mapping luôn có ảnh nền
        #     AGVConfig.img_mapping = AGVConfig.img.copy()
        
        # _last_che_do_tao_ban_do = AGVConfig.che_do_tao_ban_do
        # print(AGVConfig.che_do_tao_ban_do)
        # time.sleep(0.1) # Tăng tần suất kiểm tra (10Hz) để xử lý watchdog kịp thời

if __name__ == '__main__':
    # Đảm bảo luồng mô phỏng chỉ chạy 1 lần trong tiến trình xử lý chính
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # Khởi tạo bộ xử lý lidar chỉ một lần trong tiến trình chính
        process_handler = process.xu_ly_du_lieu_lidar()
        threading.Thread(target=icp_simulation_loop, args=(process_handler,), daemon=True).start()
    

    # Chạy server. Nếu muốn dừng việc chạy 2 lần hoàn toàn, thêm use_reloader=False
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=True)