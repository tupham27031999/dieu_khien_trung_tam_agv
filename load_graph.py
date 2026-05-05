
import os
import json
import numpy as np
import cv2
from libs_file import remove
import math
CHI_PHI_DIEM_DUNG = 20 # Chi phí cho mỗi điểm dừng/chặng trên đường đi. Có thể điều chỉnh giá trị này.

def load_points(name, path_folder_danh_sach_diem):
    """Tải danh sách điểm từ file json vào danh_sach_diem"""
    danh_sach_diem = {}
    path = os.path.join(path_folder_danh_sach_diem, f"{name}.json")
    print(f"Loading points from: {path}")
    print(f"Path exists: {os.path.exists(path)}")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                danh_sach_diem = json.load(f)
        except:
            danh_sach_diem = {}
    else:
        danh_sach_diem = {}
    return danh_sach_diem

def load_paths(name, path_folder_danh_sach_duong):
    """Tải danh sách đường từ file json vào danh_sach_duong"""
    danh_sach_duong = {}
    path = os.path.join(path_folder_danh_sach_duong, f"{name}.json")
    print(f"Loading paths from: {path}")
    print(f"Path exists: {os.path.exists(path)}")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                danh_sach_duong = json.load(f)
        except:
            danh_sach_duong = {}
    else:
        danh_sach_duong = {}
    return danh_sach_duong

def tinh_goc_cuc_bo(A, B, C, danh_sach_diem):
    import math
    xA, yA = danh_sach_diem[A][:2]
    xB, yB = danh_sach_diem[B][:2]
    xC, yC = danh_sach_diem[C][:2]

    v1 = (xB - xA, yB - yA)
    v2 = (xC - xB, yC - yB)

    dot = v1[0]*v2[0] + v1[1]*v2[1]
    mag1 = math.hypot(*v1)
    mag2 = math.hypot(*v2)

    if mag1 == 0 or mag2 == 0:
        return 180

    cos = max(-1, min(1, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos))
# --- Hàm tính khoảng cách Euclid ---
def heuristic(p1, p2):
    # print(p1,p2)
    # print("AGVConfig.danh_sach_diem", AGVConfig.danh_sach_diem)
    x1, y1 = danh_sach_diem[p1][:2]
    x2, y2 = danh_sach_diem[p2][:2]
    return math.hypot(x2 - x1, y2 - y1)
def get_edge_cost(p1, p2):
    """
    Tính chi phí thực tế để đi từ p1 đến p2, bao gồm cả chi phí tăng thêm.
    """
    # Chi phí cơ bản = khoảng cách + chi phí cho một điểm dừng
    cost = heuristic(p1, p2) + CHI_PHI_DIEM_DUNG
    return cost
def toi_uu_hoa_duong_di(path, nguong_goc=5):
    """
    Tối ưu hóa đường đi bằng cách loại bỏ các điểm trung gian nằm trên đường thẳng.
    Giữ lại các điểm nằm trong danh sách điểm đặc biệt (từ config).
    Trả về đường đi đã tối ưu và tổng chi phí của nó.
    """
    # list_loai_2 = loc_diem_theo_ky_tu_dau(cfg.data_di_chuyen_luon["loai_2"]["danh_sach_diem_dich"][0], webserver.danh_sach_diem)
    list_loai_2 = []
    list_loai_3 = []
    danh_sach_diem_dac_biet = set(list_loai_2 + list_loai_3)

    if not path:
        return [], 0.0

    # Nếu đường đi quá ngắn để tối ưu, chỉ tính chi phí
    if len(path) < 3:
        cost = 0.0
        if len(path) == 2:
            cost = get_edge_cost(path[0], path[1])
        return path, cost

    optimized_path = [path[0]]
    total_cost = 0.0
    current_idx = 0

    while current_idx < len(path) - 1:
        best_k = current_idx + 1
        
        p_start = path[current_idx]
        p_next = path[current_idx+1]
        
        if p_start not in danh_sach_diem or p_next not in danh_sach_diem:
             optimized_path.append(p_next)
             # Tính chi phí cho đoạn không tối ưu được
             total_cost += get_edge_cost(p_start, p_next)
             current_idx += 1
             continue

        x_start, y_start = danh_sach_diem[p_start][:2]
        x_next, y_next = danh_sach_diem[p_next][:2]
        v_base = (x_next - x_start, y_next - y_start)

        # Duyệt các điểm tiếp theo để xem có thể đi thẳng tới đâu
        for k in range(current_idx + 2, len(path)):
            p_middle = path[k-1]
            p_target = path[k]

            # Điều kiện 1: Điểm giữa không được là điểm đặc biệt
            if p_middle in danh_sach_diem_dac_biet:
                break
            
            if p_middle not in danh_sach_diem or p_target not in danh_sach_diem:
                break

            # Điều kiện 2: Góc cục bộ (P_prev -> P_middle -> P_target) nhỏ hơn ngưỡng
            p_prev = path[k-2]
            goc_cuc_bo = tinh_goc_cuc_bo(p_prev, p_middle, p_target, danh_sach_diem)
            if goc_cuc_bo > nguong_goc:
                break

            # Điều kiện 3: Góc giữa vector gốc (P_start -> P_next) và vector tới đích (P_start -> P_target) nhỏ hơn ngưỡng
            x_target, y_target = danh_sach_diem[p_target][:2]
            v_target = (x_target - x_start, y_target - y_start)
            
            dot = v_base[0]*v_target[0] + v_base[1]*v_target[1]
            mag_base = math.hypot(*v_base)
            mag_target = math.hypot(*v_target)
            
            angle_deviation = 0
            if mag_base > 0 and mag_target > 0:
                cos_val = max(-1, min(1, dot / (mag_base * mag_target)))
                angle_deviation = math.degrees(math.acos(cos_val))
            
            if angle_deviation > nguong_goc:
                break
            
            best_k = k
        
        segment_start = path[current_idx]
        segment_end = path[best_k]

        optimized_path.append(segment_end)
        total_cost += get_edge_cost(segment_start, segment_end)
        
        current_idx = best_k
        
    return optimized_path, total_cost
def tao_graph(danh_sach_duong):
    graph = {}
    for key, value in danh_sach_duong.items():
        (a, b) = value[0]  # Lấy cặp điểm (a, b) từ danh_sach_duong
        direction = value[1]  # Lấy hướng đi từ danh_sach_duong

        if direction == "none" or direction == "curve":  # Đường 2 chiều
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)
        else:
            # direction dạng "P1-P4" -> chỉ có hướng P1 → P4
            start, end = direction.split("-")
            graph.setdefault(start, []).append(end)
    # print("graph: ", graph)
    return graph

def tao_graph_cai_tien(danh_sach_duong, danh_sach_diem, must_keep_nodes=None, nguong_goc=5):
    """
    Tạo đồ thị đã được tối ưu hóa: gộp các đoạn thẳng liên tiếp có góc lệch nhỏ.
    Nếu 3 điểm liên tiếp n1-node-n2 tạo thành một đường gần thẳng, node sẽ được loại bỏ
    để nối trực tiếp n1 với n2, giúp AGV coi chuỗi điểm là một đường duy nhất.
    """
    # 1. Tạo graph thô ban đầu từ danh sách đường
    graph = tao_graph(danh_sach_duong)
    
    # 2. Xác định các điểm quan trọng không được phép xóa (điểm start/goal của AGV)
    diem_quan_trong = set(must_keep_nodes) if must_keep_nodes else set()

    # 3. Tiến hành gộp các node trung gian cho đến khi không còn node nào gộp được
    tiep_tuc = True
    while tiep_tuc:
        tiep_tuc = False
        # Lấy danh sách node hiện tại (không thuộc nhóm quan trọng)
        potential_nodes = [n for n in list(graph.keys()) if n not in diem_quan_trong and n in danh_sach_diem]
        
        for node in potential_nodes:
            if node not in graph: continue

            # Tìm các node trỏ tới 'node' (parents) và 'node' trỏ tới (children)
            parents = [p for p, neighbors in graph.items() if node in neighbors]
            children = graph.get(node, [])
            
            # Tập hợp các điểm kết nối trực tiếp với node này
            connected_nodes = list(set(parents) | set(children))
            
            # Điều kiện 1: Node chỉ nối với đúng 2 điểm khác (đóng vai trò là điểm trung chuyển trên 1 đường)
            if len(connected_nodes) == 2:
                n1, n2 = connected_nodes
                if n1 not in danh_sach_diem or n2 not in danh_sach_diem: continue

                # Điều kiện 2: Kiểm tra tính thông suốt (không gộp các điểm ngõ cụt hoặc điểm tụ)
                can_merge = True
                # Nếu là đường 1 chiều, phải đảm bảo n1 -> node -> n2 hoặc ngược lại
                if not ((n1 in parents and n2 in children) or (n2 in parents and n1 in children)):
                    # Nếu không phải luồng xuyên suốt, chỉ cho phép gộp nếu là đường 2 chiều cả 2 phía
                    if not (node in children and n1 in children and node in graph.get(n2, []) and n2 in graph.get(node, [])):
                        can_merge = False
                
                if not can_merge: continue

                # Điều kiện 3: Tính góc lệch tại node trung gian (sai số cho phép)
                goc_lech = tinh_goc_cuc_bo(n1, node, n2, danh_sach_diem)
                if goc_lech <= nguong_goc:
                    # Thực hiện gộp: Thay thế 'node' bằng điểm đối diện trong danh sách lân cận của các node cha
                    for p in parents:
                        target = n2 if p == n1 else n1
                        new_neighbors = [target if x == node else x for x in graph[p]]
                        graph[p] = list(dict.fromkeys(new_neighbors))
                    
                    del graph[node]
                    tiep_tuc = True
                    break
    return graph

# if __name__ == '__main__':
if 1 == 1:
    PATH_PHAN_MEM = (os.path.dirname(os.path.realpath(__file__))).replace("\\", "/")
    path_folder_danh_sach_diem = remove.tao_folder(os.path.join(PATH_PHAN_MEM, "data_input_output", "point_lists")) # File lưu danh sách điểm
    path_folder_danh_sach_duong = remove.tao_folder(os.path.join(PATH_PHAN_MEM, "data_input_output", "path_lists")) # File lưu danh sách đường đi (đơn vị mm)
    danh_sach_diem = load_points("t1", path_folder_danh_sach_diem)
    danh_sach_duong = load_paths("t1", path_folder_danh_sach_duong)

    print("Danh sách điểm:", danh_sach_diem)
    # Danh sách điểm: {'X2': [1708, 2449, 'không hướng', 0.0], 'X1': [1703, 2309, 'không hướng', 0.0], 'X3': [2674, 2682, 'không hướng', 0.0], 'W3': [2673, 2637, 'không hướng', 0.0], 'W1': [1668, 2309
    print("Danh sách đường:", danh_sach_duong)
    # Danh sách đường: {'W3_X3': [['W3', 'X3'], 'none'], 'W1_X1': [['W1', 'X1'], 'none'], 'W2_X2': [['W2', 'X2'], 'none'], 'W3_W4': [['W3', 'W4'], 'none'], 'W4_X4': [['W4', 'X4'], 'none'], 'H213_W3'


    map_size_mm=100000.0                             # Kích thước tổng của bản đồ (mm).
    resolution_mm= 20                             # Độ phân giải của bản đồ (mm/pixel).


    # occupancy grid (pixels)
    pixels = int(np.ceil(map_size_mm / resolution_mm))
    center_px = (pixels // 2, pixels // 2)


    # px_map = (center_px[0] + pts_world[:, 0] / resolution_mm).astype(np.int32)
    # py_map = (center_px[1] - pts_world[:, 1] / resolution_mm).astype(np.int32)
    # agv 1
    # "start": [1, 0],
    # "goal": [4, 4],
    # "name": "agent0"

    data_agv = {"agv1": {"start": "G21", "goal": "G42"},
                "agv2": {"start": "G22", "goal": "G41"},
                "agv3": {"start": "G23", "goal": "G44"}
                # "agv4": {"start": "G24", "goal": "G53"},
                # "agv5": {"start": "G25", "goal": "G24"},
                # "agv6": {"start": "G74", "goal": "X3"},
                # "agv7": {"start": "G75", "goal": "G65"}
                }

    graph = tao_graph(danh_sach_duong)

    # Chuyển đổi toàn bộ danh_sach_diem (bao gồm cả các điểm control của curve) sang tọa độ mm
    for name, val in danh_sach_diem.items():
        if isinstance(val, list) and len(val) >= 2:
            px, py = val[0], val[1]
            val[0] = (px - center_px[0]) * resolution_mm
            val[1] = (center_px[1] - py) * resolution_mm

    print("graph: \n", graph)

    print("Danh sách điểm sau khi chuyển sang mm: \n", danh_sach_diem)
    print("Danh sách đường sau khi chuyển sang mm: \n", danh_sach_duong)

# graph được in ra có giá trị như sau, sau khi đã tối ưu hóa bằng cách gộp các node trung gian trên các đoạn thẳng có góc lệch nhỏ:
# graph:   {'W3': ['X3', 'W4', 'H213'], 'X3': ['W3'], 'W4': ['W3', 'X4'], 'X4': ['W4'], 'H213': ['W3', 'H210', 'G35'], 
# 'G21': ['G31', 'G11', 'C1'], 'G31': ['G21', 'G41', 'C1'], 'G41': ['G31', 'H21'], 'G22': ['H14', 'G42'], 
# 'G42': ['G22', 'H24'], 'G23': ['H27', 'H17'], 'H17': ['G23', 'H07', 'X2', 'X1', 'H110', 'H14'], 
# 'H110': ['G44', 'H010', 'X2', 'C2', 'H17'], 'G44': ['H110', 'H210'], 'G35': ['H213', 'G25', 'C2'], 
# 'G25': ['G35', 'G15', 'C2'], 'H21': ['H24', 'G41'], 'H24': ['H21', 'H27', 'G42'], 'H27': ['H24', 'H210', 'G23'], 
# 'H210': ['H27', 'H213', 'G44'], 'H07': ['H17', 'H05', 'H010', 'H04'], 'H010': ['H110', 'H07', 'C2'], 
# 'X2': ['H17', 'H110', 'W2'], 'W2': ['X2', 'W1'], 'H05': ['H07', 'H04', 'W1'], 'H04': ['H05', 'C1', 'H07', 'H14'], 
# 'W1': ['H05', 'X1', 'W2'], 'X1': ['W1', 'H14', 'H17'], 'H14': ['X1', 'C1', 'H17', 'H04', 'G22'], 'G11': ['G21', 'C1'], 
# 'G15': ['G25', 'C2'], 'C1': ['H14', 'H04', 'G11', 'G21', 'G31'], 'C2': ['H110', 'H010', 'G25', 'G15', 'G35']}