import os
import cv2
import json
from flask import Flask, render_template, url_for, jsonify, request, Response, send_from_directory
from config import AGVConfig
import socket
import config
import requests
import shutil
from datetime import datetime
import numpy as np
import time
from urllib.parse import urlparse


def get_local_ip():
    """
    Tự động lấy địa chỉ IPv4 của máy tính trong mạng LAN.
    """
    s = None
    try:
        # Tạo một socket để kết nối ra ngoài.
        # Không cần gửi dữ liệu, chỉ cần thực hiện kết nối để hệ điều hành AGV_ENDPOINTS
        # chọn interface mạng phù hợp.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)) # 8.8.8.8 là DNS của Google
        ip_address = s.getsockname()[0]
        return ip_address
    except Exception as e:
        print(f"Không thể tự động lấy địa chỉ IP, sử dụng '127.0.0.1'. Lỗi: {e}")
        return "127.0.0.1" # Trả về localhost nếu có lỗi
    finally:
        if s:
            s.close()


# --- Cấu hình thời gian ---
AGV_UPDATE_INTERVAL = 1.0  # Thời gian nghỉ giữa các lần gửi dữ liệu (giây)

# --- Cấu hình API Điều khiển trung tâm (API Khác) ---
CHE_DO_API_TRUNG_TAM = False # Biến ON/OFF chế độ giao tiếp API khác
URL_API_TRUNG_TAM = "http://apbivnwb06:1332/api/AgvApi/update-status" # Thay đổi URL này thành API thực tế

CHE_DO_SENT_DATA_AGV = False # Biến ON/OFF chế độ gửi dữ liệu đến AGV


gui_dieu_khien_trung_tam = {
    "agv1": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv2": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv3": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv4": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv5": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv6": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv7": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
}

dieu_khien_trung_tam_gui = {
    "agv1": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv2": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv3": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv4": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv5": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv6": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv7": {"dich_den": "", "trang_thai": "", "message": ""},
}

# Khởi tạo ứng dụng Flask
# template_folder: nơi chứa file html (templates)
# static_folder: nơi chứa css, js, images (static)
app = Flask(__name__)

# Nạp cấu hình (nếu cần dùng app.config['KEY'])
app.config.from_object(AGVConfig)


def convert_danh_sach_duong_di(p_actual):
    # AGVConfig.danh_sach_diem
    danh_sach_duong_di = []
    for i in range(len(p_actual)):
        x = AGVConfig.danh_sach_diem[p_actual[i]][0]
        y = AGVConfig.danh_sach_diem[p_actual[i]][1]
        danh_sach_duong_di.append([x, y])
    return danh_sach_duong_di

def update_agv_states():
    """
    Hàm cập nhật AGV_STATES dựa trên thông tin người dùng chọn (thong_tin_da_chon)
    và các biến điều khiển khác (dich_den_gui_agv).
    """
    # lấy thông tin đã chọn trên web
    for agv in AGVConfig.DANH_SACH_AGV:
        # Lấy thông tin cấu hình hiện tại của AGV
        user_config = AGVConfig.thong_tin_da_chon.get(agv, {})
        if (user_config.get("che_do_dieu_khien_truc_tiep") == "on") == True:
            # continue # Nếu chế độ điều khiển trực tiếp tắt, bỏ qua cập nhật trạng thái cho AGV này
            # 1. Cập nhật đích đến
            AGVConfig.AGV_STATES[agv]["dich_den"] = AGVConfig.dich_den_gui_agv.get(agv, "")
            
            # 2. Cập nhật trạng thái gửi AGV (logic: tra_hang/lay_hang -> giữ nguyên, khác -> nang)
            chon_gia = user_config.get("chon_gia_hang", "")
            if chon_gia == "tra_hang":
                AGVConfig.AGV_STATES[agv]["trang_thai_gui_agv"] = "tra_hang"
            elif chon_gia == "lay_hang":
                AGVConfig.AGV_STATES[agv]["trang_thai_gui_agv"] = "lay_hang"
            else:
                AGVConfig.AGV_STATES[agv]["trang_thai_gui_agv"] = "nang"
                
            # 3. Cập nhật đường đi (Paths) - Tạm thời để rỗng
            # AGVConfig.AGV_STATES[agv]["paths"] = []
            
            # 4. Cập nhật các cờ Boolean (Chuyển đổi từ 'on'/'off' sang True/False)
            AGVConfig.AGV_STATES[agv]["di_chuyen_khong_hang"] = (user_config.get("di_chuyen_khong_hang") == "on")
            AGVConfig.AGV_STATES[agv]["che_do_dieu_khien_truc_tiep"] = (user_config.get("che_do_dieu_khien_truc_tiep") == "on")

        # if agv == "agv1": # Chỉ in trạng thái của agv1 để kiểm tra (bạn có thể thay đổi hoặc bỏ qua)
        #     print(AGVConfig.AGV_STATES[agv]) # In trạng thái AGV sau khi cập nhật để kiểm tra
        # chuyển đổi danh sách đường đi sang tọa độ đường đi
        # AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(AGVConfig.AGV_STATES[agv]["danh_sach_duong_di"])
        # test
        # if agv == "agv1":
        #     AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(["G35", "G34", "W3"])
        #     AGVConfig.AGV_STATES[agv]["goc_agv"] = 30
        # elif agv == "agv2":
        #     AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(["P53", "P50"])
            
        #     AGVConfig.AGV_STATES[agv]["goc_agv"] = 40
        # elif agv == "agv3":
        #     AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(["P43", "P40"])
        #     AGVConfig.AGV_STATES[agv]["goc_agv"] = 50
        # elif agv == "agv4":
        #     AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(["P48", "G35", "G36"])
        #     AGVConfig.AGV_STATES[agv]["goc_agv"] = 60
        # elif agv == "agv5":
        #     AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(["P19", "P18", "P17"])
        #     AGVConfig.AGV_STATES[agv]["goc_agv"] = 70
        # elif agv == "agv6":
        #     AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(["P13", "P12", "P11"])
        #     AGVConfig.AGV_STATES[agv]["goc_agv"] = 80
        # elif agv == "agv7":
        #     AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"] = convert_danh_sach_duong_di(["P76", "G28", "W1"])
        #     AGVConfig.AGV_STATES[agv]["goc_agv"] = 90
        # AGVConfig.AGV_STATES[agv]["toa_do"] = {"x": AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"][0][0], "y": AGVConfig.AGV_STATES[agv]["danh_sach_toa_do_duong_di"][0][1]}





    if CHE_DO_SENT_DATA_AGV:
        data_to_send_all = AGVConfig.AGV_STATES
        # Gửi yêu cầu đến từng AGV
        for agv_id, endpoint in AGVConfig.AGV_ENDPOINTS.items():
            try:
                # Gửi dữ liệu của tất cả AGV cho mỗi AGV
                response = requests.post(endpoint, json=data_to_send_all, timeout=1)
                if response.status_code == 200:
                    response_data = response.json()
                    data_from_agv = response_data.get("data")
                    # Chỉ cập nhật nếu có 'data' và có key của agv_id tương ứng
                    if data_from_agv and agv_id in data_from_agv:
                        received_state = data_from_agv[agv_id]
                        if received_state:
                            # Cập nhật tất cả thông tin từ AGV
                            AGVConfig.AGV_STATES[agv_id].update(received_state)
                            
                            # Cập nhật thông tin IP kết nối và thời gian
                            parsed = urlparse(endpoint)
                            AGVConfig.danh_sach_ip_ket_noi[agv_id] = {
                                "address": parsed.netloc,
                                "last_seen": time.time()
                            }

                    print(f"Nhận phản hồi từ {agv_id}: {AGVConfig.AGV_STATES[agv_id]}")
                else:
                    print(f"Lỗi khi giao tiếp với {agv_id}: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Lỗi kết nối đến {agv_id} ({endpoint}): {e}")

    if CHE_DO_API_TRUNG_TAM:
        try:
            # 1. Chuẩn bị dữ liệu gửi đi (dạng gui_dieu_khien_trung_tam)
            payload_trung_tam = []
            for agv_id in AGVConfig.DANH_SACH_AGV:
                try:
                    agv_num = int(agv_id.replace("agv", ""))
                except:
                    agv_num = 0
                payload_trung_tam.append({
                    "AGV_ID": agv_num,
                    "Trang_thai": AGVConfig.AGV_STATES[agv_id]["trang_thai_gui_agv"],
                    "Vi_tri_hien_tai": AGVConfig.AGV_STATES[agv_id]["vi_tri_hien_tai"],
                    "mgs": AGVConfig.AGV_STATES[agv_id]["message"]
                })
            # ví dụ
            payload_trung_tam = [{  "AGV_ID": 1,
                                    "Trang_thai": "PICKING",
                                    "Vi_tri_hien_tai": "A_02",
                                    "mgs": ""},
                                {   "AGV_ID": 2,
                                    "Trang_thai": "IDLE",
                                    "Vi_tri_hien_tai": "M00",
                                    "mgs": "test"}]
            # IDLE,       // Nghỉ / Chờ lệnh
            # PICKING,    // Đang lấy hàng
            # DROPPING,   // Đang trả hàng
            # CHARGING,   // Đang sạc
            # BLOCKED,    // Bị vật cản
            # ERROR,      // Lỗi kỹ thuật
            # OFFLINE     // Mất kết nối
            # 2. Gửi request
            response_tt = requests.post(URL_API_TRUNG_TAM, json=payload_trung_tam, timeout=1)
            # {'status': 'Success', 
            #  'commands': [{'agV_ID': 1, 'dich_den': 'B01', 'message': 'Moving to: B01', 'action': 'MOVE'}, 
            #               {'agV_ID': 2, 'dich_den': 'HOME', 'message': 'Moving to: HOME', 'action': 'MOVE'}]}
            # 3. Xử lý phản hồi (dạng dieu_khien_trung_tam_gui)
            if response_tt.status_code == 200:
                data_tt = response_tt.json()
                print(f"Nhận từ API trung tâm: {data_tt}")
                if "commands" in data_tt and isinstance(data_tt["commands"], list):
                    for cmd in data_tt["commands"]:
                        agv_id_num = cmd.get("agV_ID")
                        agv_key = f"agv{agv_id_num}"
                        dich_den = cmd.get("dich_den")

                        dich_den_new = None
                        for _, point_data in AGVConfig.BAN_DO_KE.items():
                            for item in point_data:
                                # item cấu trúc ["TenKe", "TenDiem"]
                                if item[0] == dich_den:
                                    dich_den_new = item[1]
                                    break
                            if dich_den_new:
                                break
                        print("dich_den_new", dich_den_new)
                        if agv_key in AGVConfig.AGV_STATES:
                            # Cập nhật đích đến nếu có
                            if dich_den_new:
                                AGVConfig.AGV_STATES[agv_key]["dich_den"] = dich_den_new
        except Exception as e:
            print(f"Lỗi kết nối API trung tâm: {e}")

@app.route('/')
def home():
    """
    Route trang chủ. Render home.html và truyền các tham số từ Config.
    """
    return render_template('home.html',
                           ten_dieu_de=AGVConfig.ten_dieu_de,
                           version=AGVConfig.VERSION,
                           danh_sach_agv=AGVConfig.DANH_SACH_AGV,
                           thong_tin_hien_thi=AGVConfig.thong_tin_hien_thi,
                           lua_chon_yeu_cau=AGVConfig.lua_chon_yeu_cau,
                           cac_gia_hang=AGVConfig.cac_gia_hang,
                           ban_do_ke=AGVConfig.BAN_DO_KE,
                           cac_loai_ke=AGVConfig.CAC_LOAI_KE,
                           thong_tin_da_chon=AGVConfig.thong_tin_da_chon,
                           gia_tri_hang_hien_tai=AGVConfig.gia_tri_hang_hien_tai,
                           agv_realtime_states=AGVConfig.AGV_STATES,
                           agv_colors=AGVConfig.agv_color,
                           map_resolution=AGVConfig.map_resolution,
                           kich_thuoc_agv=AGVConfig.kich_thuoc_agv,
                           hien_thi_diem=AGVConfig.hien_thi_diem,
                           hien_thi_duong=AGVConfig.hien_thi_duong)

@app.route('/api/get_info')
def get_info():
    """
    API trả về thông tin hiển thị mới nhất để JS cập nhật.
    """
    update_agv_states() # Cập nhật trạng thái mới nhất trước khi trả về (đảm bảo tính liên tục)
    return jsonify({
        'info': AGVConfig.thong_tin_hien_thi,
        'agv_states': AGVConfig.AGV_STATES
    })

@app.route('/api/send_request', methods=['POST'])
def send_request():
    """
    API nhận dữ liệu cấu hình khi nhấn nút Gửi.
    Lưu cấu hình vào config và bật cờ trang_thai_gui = True
    """
    data = request.json
    agv_name = data.get('agv_name')
    state = data.get('state')
    
    if agv_name and state:
        AGVConfig.thong_tin_da_chon[agv_name] = state
        AGVConfig.trang_thai_gui[agv_name] = True
        
        # Reset chỉ số về 0 khi gửi danh sách mới
        danh_sach = state.get("danh_sach_ke_da_chon", [])
        AGVConfig.chi_so_hang_hien_tai[agv_name] = 0
        if danh_sach and len(danh_sach) > 0:
            AGVConfig.gia_tri_hang_hien_tai[agv_name] = danh_sach[0]
            
            # Logic tìm điểm đích cho phần tử đầu tiên (Index 0) ngay khi gửi
            dich_den = ""
            for _, point_data in AGVConfig.BAN_DO_KE.items():
                for item in point_data:
                    # item cấu trúc ["TenKe", "TenDiem"]
                    if item[0] == danh_sach[0]:
                        dich_den = item[1]
                        break
                if dich_den != "":
                    break
            AGVConfig.dich_den_gui_agv[agv_name] = dich_den
            
        else:
            AGVConfig.gia_tri_hang_hien_tai[agv_name] = ""
            AGVConfig.dich_den_gui_agv[agv_name] = ""
            
        update_agv_states() # Cập nhật AGV_STATES ngay sau khi thay đổi cấu hình
        return jsonify({'status': 'success', 'message': 'Đã gửi yêu cầu'})
    return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ'}), 400

@app.route('/api/map_image')
def map_image(): # This function is duplicated, consider removing one instance.
    """
    API trả về ảnh bản đồ trực tiếp từ bộ nhớ (numpy array -> png).
    Không cần lưu file ra đĩa.
    """
    # Mã hóa ảnh numpy (BGR) sang định dạng PNG
    is_success, buffer = cv2.imencode(".png", AGVConfig.img)
    if is_success:
        return Response(buffer.tobytes(), mimetype='image/png')
    return "Error encoding image", 500

@app.route('/api/save_markers', methods=['POST'])
def save_markers():
    """Lưu danh sách các điểm đánh dấu (giá kệ) vào file JSON."""
    try:
        markers = request.json.get('markers', [])
        with open(AGVConfig.path_markers, 'w', encoding='utf-8') as f:
            json.dump(markers, f, ensure_ascii=False, indent=4)
        return jsonify({'status': 'success', 'message': 'Đã lưu bản đồ thành công!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_markers')
def get_markers():
    """Đọc danh sách các điểm đánh dấu từ file JSON."""
    if not os.path.exists(AGVConfig.path_markers):
        return jsonify({'markers': []})
    try:
        with open(AGVConfig.path_markers, 'r', encoding='utf-8') as f:
            markers = json.load(f)
        return jsonify({'markers': markers})
    except:
        return jsonify({'markers': []})

@app.route('/api/save_occupied_points', methods=['POST'])
def save_occupied_points():
    """Lưu cấu hình điểm chiếm dụng (khóa điểm)."""
    try:
        data = request.json.get('rules', {})
        AGVConfig.diem_chiem_dung = data
        with open(AGVConfig.path_diem_chiem_dung, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return jsonify({'status': 'success', 'message': 'Đã lưu cấu hình khóa điểm!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_occupied_points')
def get_occupied_points():
    """Lấy cấu hình điểm chiếm dụng."""
    if not os.path.exists(AGVConfig.path_diem_chiem_dung):
        return jsonify({})
    return jsonify(AGVConfig.diem_chiem_dung)

@app.route('/api/get_uploaded_files')
def get_uploaded_files():
    """Lấy danh sách các file đang nằm trong thư mục upload chờ được Apply."""
    files = os.listdir(AGVConfig.path_folder_upload)
    return jsonify({'files': files})

@app.route('/api/upload_update_file', methods=['POST'])
def upload_update_file():
    """API nhận file cập nhật (ví dụ từ AGV quét bản đồ gửi lên)."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy file'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Tên file trống'}), 400

    save_path = os.path.join(AGVConfig.path_folder_upload, file.filename)
    file.save(save_path)
    return jsonify({'status': 'success', 'message': f'Đã tải lên {file.filename}'})

@app.route('/api/clear_upload_folder', methods=['POST'])
def clear_upload_folder():
    """API xóa sạch thư mục upload nếu người dùng muốn dọn dẹp thủ công."""
    try:
        for filename in os.listdir(AGVConfig.path_folder_upload):
            file_path = os.path.join(AGVConfig.path_folder_upload, filename)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        return jsonify({'status': 'success', 'message': 'Đã dọn dẹp thư mục upload.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/apply_update', methods=['POST'])
def apply_update():
    """
    Thực hiện cập nhật file từ folder upload vào hệ thống và backup file cũ.
    """
    try:
        if not os.path.exists(AGVConfig.path_download_json):
            return jsonify({'status': 'error', 'message': 'Không tìm thấy file download.json cấu hình'}), 404

        with open(AGVConfig.path_download_json, 'r', encoding='utf-8') as f:
            config_update = json.load(f)

        master_ip = config_update.get('download_ip')
        master_port = config_update.get('port', 5000)
        files_to_update = config_update.get('files', [])
        updated_count = 0
        
        # Nếu có download_ip, thực hiện tải file từ máy đó về trước
        if master_ip:
            for item in files_to_update:
                target_rel_path = item['target'].lstrip('/')
                filename = item['name']
                remote_url = f"http://{master_ip}:{master_port}/api/download_update/{target_rel_path}"
                try:
                    r = requests.get(remote_url, timeout=10)
                    if r.status_code == 200:
                        with open(os.path.join(AGVConfig.path_folder_upload, filename), 'wb') as f:
                            f.write(r.content)
                    else:
                        return jsonify({'status': 'error', 'message': f"Lỗi {r.status_code} khi tải {filename}"}), 500
                except Exception as e:
                    return jsonify({'status': 'error', 'message': f"Không thể kết nối tới AGV {master_ip}: {str(e)}"}), 500

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(AGVConfig.path_backup, timestamp)
        os.makedirs(backup_dir, exist_ok=True)

        backup_manifest_entries = []

        for item in files_to_update:
            filename = item['name']
            # target_path là đường dẫn tương đối tính từ PATH_PHAN_MEM
            target_rel_path = item['target'].lstrip('/')
            source_path = os.path.join(AGVConfig.path_folder_upload, filename)
            final_target_path = os.path.join(AGVConfig.PATH_PHAN_MEM, target_rel_path)

            if os.path.exists(source_path):
                # 1. Backup file cũ nếu tồn tại
                if os.path.exists(final_target_path):
                    shutil.copy2(final_target_path, os.path.join(backup_dir, filename))
                    backup_manifest_entries.append({
                        "filename": filename,
                        "original_target_rel_path": target_rel_path
                    })
                
                # 2. Đảm bảo thư mục đích tồn tại
                os.makedirs(os.path.dirname(final_target_path), exist_ok=True)
                
                # 3. Ghi đè file mới
                shutil.move(source_path, final_target_path)
                
                updated_count += 1
        
        # Lưu backup_manifest.json nếu có file được backup
        if backup_manifest_entries:
            with open(os.path.join(backup_dir, "backup_manifest.json"), 'w', encoding='utf-8') as f:
                json.dump({"timestamp": timestamp, "files_backed_up": backup_manifest_entries}, f, indent=4, ensure_ascii=False)

        # Reload map nếu có cập nhật log_odds.npy
        if any(f['name'] == 'log_odds.npy' for f in files_to_update):
            if os.path.exists(AGVConfig.path_map):
                AGVConfig.img = config.get_occupancy_image(log_odds_map=np.load(AGVConfig.path_map))

        return jsonify({
            'status': 'success', 
            'message': f'Cập nhật thành công {updated_count} file. Bản cũ lưu tại {timestamp}'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/list_backups')
def list_backups():
    """
    API liệt kê tất cả các bản sao lưu có sẵn trong thư mục config.path_backup.
    Mỗi bản sao lưu là một thư mục có tên là timestamp.
    """
    backups = []
    if not os.path.exists(AGVConfig.path_backup):
        return jsonify(backups)

    for entry in os.listdir(AGVConfig.path_backup):
        backup_path = os.path.join(AGVConfig.path_backup, entry)
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

    source_path = os.path.join(AGVConfig.path_backup, timestamp, filename)
    destination_path = os.path.join(AGVConfig.PATH_PHAN_MEM, original_target_rel_path)

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

@app.route('/api/deploy_to_all_agvs', methods=['POST'])
def deploy_to_all_agvs():
    """
    Lệnh này chạy trên Master Server. 
    Nó quét danh sách AGV_ENDPOINTS và ra lệnh cho các AGV đó gọi lại chính nó để cập nhật.
    """
    my_ip = get_local_ip()
    results = {}
    
    # Duyệt qua các AGV trong mạng (Sử dụng IP từ AGV_ENDPOINTS trong config)
    for agv_id, endpoint in AGVConfig.AGV_ENDPOINTS.items():
        # endpoint thường là http://IP:PORT/PC_sent_AGV, ta cần đổi sang /api/sync_from_master
        base_url = endpoint.rsplit('/', 1)[0].replace('PC_sent_AGV', '').rstrip('/')
        # Giả sử các AGV con cũng chạy API ở port 5000 hoặc cùng port với endpoint
        sync_url = f"{base_url}/api/sync_from_master" 
        
        try:
            resp = requests.post(sync_url, json={'master_ip': my_ip}, timeout=2)
            results[agv_id] = resp.json().get('message', 'OK')
        except Exception as e:
            results[agv_id] = f"Lỗi: {str(e)}"
            
    return jsonify({'status': 'success', 'details': results})

@app.route('/api/get_sync_manifest')
def get_sync_manifest():
    """API cho các AGV khác gọi để biết cần tải những file nào."""
    if os.path.exists(AGVConfig.path_download_json):
        return send_from_directory(os.path.dirname(AGVConfig.path_download_json), 'download.json')
    return jsonify({'files': []})

@app.route('/api/download_update/<path:filepath>')
def download_update_file_agv(filepath):
    """API cho các AGV khác tải file cập nhật."""
    return send_from_directory(AGVConfig.PATH_PHAN_MEM, filepath)

@app.route('/api/get_graph_data')
def get_graph_data():
    """
    API đọc file danh sách điểm và danh sách đường, gửi về client cùng kích thước ảnh map.
    """
    points_map = {}
    paths_list = []
    h, w = AGVConfig.img.shape[:2]

    try:
        # 1. Đọc danh sách ĐIỂM
        # print(AGVConfig.path_danh_sach_diem, os.path.exists(AGVConfig.path_danh_sach_diem))
        if os.path.exists(AGVConfig.path_danh_sach_diem):
            with open(AGVConfig.path_danh_sach_diem, 'r', encoding='utf-8') as f:
                data_points = json.load(f)
                for key, value in data_points.items():
                    # Kiểm tra định dạng điểm: [x, y, ...]
                    if isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float)):
                        # Chuyển đổi mm sang pixel
                        points_map[key] = {"name": key, "x": float(value[0]), "y": float(value[1])}
        print("Danh sách điểm đã đọc:", points_map)
        # 2. Đọc danh sách ĐƯỜNG
        if os.path.exists(AGVConfig.path_danh_sach_duong):
            with open(AGVConfig.path_danh_sach_duong, 'r', encoding='utf-8') as f:
                data_paths = json.load(f)
                for key, value in data_paths.items():
                    # Kiểm tra định dạng đường mới: [["Start", "End"], "type", "ControlPoint" (nếu có)]
                    if isinstance(value, list) and len(value) >= 1 and isinstance(value[0], list) and len(value[0]) >= 2:
                        nodes = value[0]
                        start_node = nodes[0]
                        end_node = nodes[1]
                        path_type = value[1] if len(value) > 1 else "none"
                        control_node = value[2] if len(value) > 2 else None

                        if start_node in points_map and end_node in points_map:
                            path_item = {
                                "start": points_map[start_node],
                                "end": points_map[end_node],
                                "type": path_type,
                                "start_node": start_node,
                                "end_node": end_node
                            }
                            if path_type == "curve" and control_node in points_map:
                                path_item["control"] = points_map[control_node]
                            paths_list.append(path_item)
        print("Danh sách đường đã đọc:", paths_list)
        return jsonify({'points': list(points_map.values()), 'paths': paths_list, 'dims': [w, h]})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_connected_agvs')
def get_connected_agvs():
    """API trả về danh sách các AGV đang kết nối và thời gian phản hồi cuối."""
    now = time.time()
    data = []
    for agv_id in AGVConfig.DANH_SACH_AGV:
        info = AGVConfig.danh_sach_ip_ket_noi.get(agv_id)
        
        if info:
            address = info["address"]
            seconds_ago = int(now - info["last_seen"])
        else:
            # Lấy địa chỉ từ cấu hình endpoint nếu AGV chưa từng phản hồi
            endpoint = AGVConfig.AGV_ENDPOINTS.get(agv_id)
            if endpoint:
                address = urlparse(endpoint).netloc
            else:
                address = "Chưa cấu hình"
            seconds_ago = 999999 # Giá trị lớn biểu thị chưa bao giờ kết nối
            
        data.append({
            "id": agv_id,
            "address": address,
            "seconds_ago": seconds_ago
        })
    return jsonify(data)

@app.route('/api/send_complete', methods=['POST'])
def send_complete():
    """
    API nhận tín hiệu hoàn thành từ nút nhấn giả lập.
    """
    data = request.json
    agv_name = data.get('agv_name')
    
    if agv_name:
        AGVConfig.trang_thai_hoan_thanh[agv_name] = True
        
        # Logic: Tăng index lên 1, nếu hết danh sách thì quay về 0 (vòng lặp)
        danh_sach = AGVConfig.thong_tin_da_chon[agv_name].get("danh_sach_ke_da_chon", [])
        if danh_sach and len(danh_sach) > 0:
            hien_tai = AGVConfig.chi_so_hang_hien_tai.get(agv_name, 0)
            tiep_theo = (hien_tai + 1) % len(danh_sach) # Phép chia lấy dư để tạo vòng lặp
            
            AGVConfig.chi_so_hang_hien_tai[agv_name] = tiep_theo # index ví dụ  0, 1, 2... và sẽ quay về 0 sau khi vượt quá độ dài danh sách
            AGVConfig.gia_tri_hang_hien_tai[agv_name] = danh_sach[tiep_theo] # giá trị hàng hiện tại (ví dụ: "B01")

            # tìm điểm tương ứng với giá hàng tiếp theo để gửi cho AGV từ BAN_DO_KE
            dich_den = ""
            for point_name, point_data in AGVConfig.BAN_DO_KE.items():
                for item in point_data:
                    if item[0] == danh_sach[tiep_theo]: # nếu tên giá hàng trùng với tên trong BAN_DO_KE
                        dich_den = item[1] # lấy điểm tương ứng để gửi cho AGV
                        break
                if dich_den != "":
                    break

            if dich_den != "":
                AGVConfig.dich_den_gui_agv[agv_name] = dich_den

            print(f"{agv_name} hoàn thành. Chuyển sang {danh_sach[tiep_theo]} (index {tiep_theo})")

            update_agv_states() # Cập nhật AGV_STATES sau khi đổi đích đến
            
            return jsonify({'status': 'success', 'message': f'{agv_name} hoàn thành. Tiếp theo: {danh_sach[tiep_theo]}'})
            
        return jsonify({'status': 'success', 'message': f'{agv_name} đã hoàn thành (không có danh sách)'})
    return jsonify({'status': 'error', 'message': 'Thiếu tên AGV'}), 400

if __name__ == '__main__':
    # Chạy server với debug=True để tự động reload khi sửa code
    app.run(host='0.0.0.0', port=5000, debug=True)