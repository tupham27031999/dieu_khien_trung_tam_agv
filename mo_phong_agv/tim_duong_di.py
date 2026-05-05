import math
import heapq
import os
import time
import json
import config_2 as cfg
from mo_phong_agv.fleet_logic_thuc_te import FleetLogicRealTime
from mo_phong_agv.simulation import AGVVisualizer
from mo_phong_agv.graph_manager import GraphManager



def load_points_route(filename): # Change parameter name to match the variable rule
    danh_sach_diem = {}
    name_file = filename.split(".")[0]
    filepath = cfg.PATH_POINTS_DIR + "/" + name_file + ".json"
    print(filepath)
    if not os.path.exists(filepath):
        print("e1")
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded_points = json.load(f)
        danh_sach_diem = loaded_points
    return danh_sach_diem


def load_paths_route(filename, danh_sach_diem=None):
    danh_sach_duong = {}
    name_file = filename.split(".")[0]
    filepath = cfg.PATH_PATHS_DIR + "/" + name_file + ".json"
    print(filepath)
    if not os.path.exists(filepath):
        print("e2")
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded_paths = json.load(f)
        
        # Validate if points for these paths exist in current danh_sach_diem
        valid_paths = {}
        for path_name, path_data in loaded_paths.items():
            (p1_name, p2_name) = path_data[0]
            direction = path_data[1]
            if p1_name in danh_sach_diem and p2_name in danh_sach_diem:
                valid_paths[path_name] = [[p1_name, p2_name], direction]
            else:
                print(f"Warning: Path '{path_name}' skipped during load. Point(s) '{p1_name}' or '{p2_name}' not in current point list.")
        
        danh_sach_duong = valid_paths
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

def normalize_angle_90(angle):
    """
    Chuẩn hóa một góc về khoảng [-90, 90] độ.
    Ví dụ: 100 -> -80, -100 -> 80.
    """
    # Dùng toán tử modulo để đưa góc về [0, 360)
    angle = angle % 360
    # Chuyển từ [0, 360) về [-180, 180)
    if angle > 180:
        angle -= 360
    # Chuyển từ [-180, 180) về [-90, 90)
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    return angle
# --- Tạo graph có hướng ---
def tao_graph(danh_sach_duong):
    graph = {}
    for key, value in danh_sach_duong.items():
        (a, b), direction = value

        if direction == "none" or direction == "curve":  # Đường 2 chiều
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)
        else:
            # direction dạng "P1-P4" -> chỉ có hướng P1 → P4
            start, end = direction.split("-")
            graph.setdefault(start, []).append(end)
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
    # Tối ưu: Xây dựng bản đồ node cha để tránh duyệt toàn bộ graph nhiều lần
    def build_parent_map(g):
        p_map = {}
        for p, neighbors in g.items():
            for n in neighbors:
                p_map.setdefault(n, set()).add(p)
        return p_map

    parent_map = build_parent_map(graph)
    tiep_tuc = True
    while tiep_tuc:
        tiep_tuc = False
        # Lấy danh sách node hiện tại (không thuộc nhóm quan trọng)
        potential_nodes = [n for n in list(graph.keys()) if n not in diem_quan_trong and n in danh_sach_diem]
        
        for node in potential_nodes:
            if node not in graph: continue

            parents = list(parent_map.get(node, []))
            children = graph.get(node, [])
            
            # Tập hợp các điểm kết nối trực tiếp với node này
            connected_nodes = list(set(parents) | set(children))
            
            # Điều kiện 1: Node chỉ nối với đúng 2 điểm khác (đóng vai trò là điểm trung chuyển trên 1 đường)
            if len(connected_nodes) == 2:
                n1, n2 = connected_nodes
                if n1 not in danh_sach_diem or n2 not in danh_sach_diem: continue

                # Điều kiện 2: Kiểm tra tính thông suốt (đảm bảo node là điểm trung chuyển trên một luồng)
                # Luồng đi: n1 -> node -> n2 HOẶC n2 -> node -> n1
                is_flow = (n1 in parents and n2 in children) or (n2 in parents and n1 in children)
                if not is_flow: continue

                # Điều kiện 3: Tính góc lệch tại node trung gian.
                # tinh_goc_cuc_bo trả về góc giữa vector n1->node và node->n2. 
                # Góc 0 độ nghĩa là thẳng hàng hoàn hảo và cùng hướng đi tới.
                goc_lech = abs(tinh_goc_cuc_bo(n1, node, n2, danh_sach_diem))

                if goc_lech <= nguong_goc:
                    # Thực hiện gộp: Thay thế 'node' bằng điểm đối diện trong danh sách lân cận của các node cha
                    for p in parents:
                        target = n2 if p == n1 else n1
                        new_neighbors = [target if x == node else x for x in graph[p]]
                        graph[p] = list(dict.fromkeys(new_neighbors))
                        # Cập nhật parent_map
                        parent_map.setdefault(target, set()).add(p)
                        if node in parent_map.get(target, set()):
                            parent_map[target].discard(node)
                    
                    # Cập nhật parent_map cho n1, n2 vì node trung gian đã mất
                    if node in parent_map: del parent_map[node]
                    
                    del graph[node]
                    tiep_tuc = True
                    break
    return graph
# def tao_duong_di_cho_agv():
    
# def creat_data_graph():
#     load_points_route("t2.json")
#     load_paths_route("t2.json")
#     tao_graph()
    # print(graph)

# creat_data_grap()



if __name__ == "__main__":
    diem_chiem_dung = {}

    # 1. Create GraphManager and populate it from loaded data
    graph_manager = GraphManager()
    graph_manager.graph = tao_graph()
    graph_manager.positions = {name: (data[0], data[1]) for name, data in danh_sach_diem.items()}

    # # 2. Khởi tạo Fleet Logic và Visualizer
    # agv_ids = ["agv1", "agv2", "agv3"]
    # fleet = FleetLogicRealTime(graph_manager, agv_ids, diem_chiem_dung)
    # visualizer = AGVVisualizer(graph_manager, agv_ids)




    # 2. Khởi tạo Fleet Logic và Visualizer
    # agv_ids = ["agv1", "agv2", "agv3"]
    agv_ids = ["agv1"]
    fleet = FleetLogicRealTime(graph_manager, agv_ids, diem_chiem_dung)
    visualizer = AGVVisualizer(graph_manager, agv_ids)

    # 3. Dữ liệu cố định ban đầu
    current_telemetry = [
        {"agv_id": "agv1", "current_node": "X1", "status": "IDLE"},
        # {"agv_id": "agv2", "current_node": "A1", "status": "IDLE"},
        # {"agv_id": "agv3", "current_node": "D2", "status": "IDLE"},
    ]
    initial_jobs = [
        {"agv_id": "agv1", "goal": "X2"},
    #     {"agv_id": "agv2", "goal": "E2"},
    #     {"agv_id": "agv3", "goal": "B2"},
    ]

    print("--- BẮT ĐẦU ĐIỀU PHỐI VÒNG LẶP ---")
    
    running = True
    active_jobs = initial_jobs
    
    while running:
        input_data = {"telemetry": current_telemetry, "jobs": active_jobs}
        print("\nINPUT CHO VÒNG LẶP:", input_data)

        commands = fleet.run_cycle(input_data)

        new_telemetry = []
        for agv_id in agv_ids:
            cmd = commands.get(agv_id, {})
            current_agv_data = fleet.agvs[agv_id]
            
            # Mặc định lấy vị trí hiện tại
            current_node = current_agv_data["current_node"]
            
            if cmd.get("command") == "DI_CHUYEN":
                path = cmd.get("path", [])
                print(f"DEBUG: AGV {agv_id} received DI_CHUYEN command with path: {path}")
                current_node = path[1] if len(path) > 1 else path[0]
                
                # Nếu node vừa tới là đích của path hiện tại
                if current_node == current_agv_data["path"][-1]:
                    status = "da_den_dich"
                    print(f"OUTPUT: {agv_id} DA_DEN_DICH {current_node}")
                else:
                    status = "dang_di_chuyen"
            else:
                # KIỂM TRA TẠI ĐÂY: 
                # Nếu không có lệnh di chuyển nhưng node hiện tại trùng với đích cũ
                if current_agv_data["goal"] and current_node == current_agv_data["goal"]:
                    status = "da_den_dich"
                elif cmd.get("command") == "TAM_DUNG":
                    status = "tam_dung"
                else:
                    status = "da_den_dich" if current_agv_data["path"] == [] else "dang_cho"

            new_telemetry.append({
                "agv_id": agv_id, 
                "current_node": current_node, 
                "status": status
            })

        current_telemetry = new_telemetry
        # ... (phần in và sleep giữ nguyên)
        
        
        print("\nTRANG_THAI_HE_THONG:", current_telemetry)
        time.sleep(1)
        if not visualizer.update_and_draw(current_telemetry, commands):
            break

        # if all(t["status"] in ["dang_cho", "da_den_dich"] for t in current_telemetry):
        #     print("--- TAT_CA_AGV_DA_HOAN_THANH ---")
        #     break

        # Cập nhật điều kiện thoát
        if all(t["status"] == "da_den_dich" for t in current_telemetry):
            print("--- TAT_CA_AGV_DA_DEN_DICH ---")
            time.sleep(2)
            break

    # pygame.quit()