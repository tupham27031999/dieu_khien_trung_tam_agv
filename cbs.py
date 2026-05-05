"""

Python implementation of Conflict-based search

author: Ashwin Bose (@atb033)

"""
import sys
sys.path.insert(0, '../')
import json
from math import fabs
from itertools import combinations
from copy import deepcopy
import numpy as np
from load_graph import tao_graph
from a_star import AStar


# Định nghĩa kích thước AGV tập trung để dễ điều chỉnh
AGENT_L_FRONT = 1550  # mm (Chiều dài từ tâm đến mũi xe)
AGENT_L_BACK = -950   # mm (Chiều dài từ tâm đến đuôi xe, âm vì nằm phía sau)
AGENT_W_HALF = 450    # mm (Bán kính ngang, tức là nửa chiều rộng của xe)
SAFETY_MARGIN = 150   # mm (điểu chỉnh để đảm bảo khoảng cách an toàn giữa các AGV)

class Location(object):
    def __init__(self, x=-1, y=-1):
        self.x = int(round(x))
        self.y = int(round(y))
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    def __str__(self):
        return str((self.x, self.y))

class State(object):
    def __init__(self, time, location, direction=0):
        self.time = time
        self.location = location
        self.direction = direction # 0-3 cho Grid, hoặc Độ (0-360) cho Graph
    def __eq__(self, other):
        return self.time == other.time and self.location == other.location and round(self.direction or 0) == round(other.direction or 0)
    def __hash__(self):
        return hash((self.time, self.location.x, self.location.y, round(self.direction or 0)))
    def is_equal_except_time(self, state):
        return self.location == state.location
    def __str__(self):
        return str((self.time, self.location.x, self.location.y))

class Conflict(object):
    VERTEX = 1
    EDGE = 2
    def __init__(self):
        self.time = -1
        self.type = -1

        self.agent_1 = ''
        self.agent_2 = ''

        self.location_1 = Location()
        self.location_2 = Location()

    def __str__(self):
        return '(' + str(self.time) + ', ' + self.agent_1 + ', ' + self.agent_2 + \
             ', '+ str(self.location_1) + ', ' + str(self.location_2) + ')'

class VertexConstraint(object):
    def __init__(self, time, location):
        self.time = time
        self.location = location

    def __eq__(self, other):
        return self.time == other.time and self.location == other.location
    def __hash__(self):
        return hash((self.time, self.location.x, self.location.y))
    def __str__(self):
        return '(' + str(self.time) + ', '+ str(self.location) + ')'

class EdgeConstraint(object):
    def __init__(self, time, location_1, location_2):
        self.time = time
        self.location_1 = location_1
        self.location_2 = location_2
    def __eq__(self, other):
        return self.time == other.time and self.location_1 == other.location_1 \
            and self.location_2 == other.location_2
    def __hash__(self):
        return hash((self.time, self.location_1.x, self.location_1.y, self.location_2.x, self.location_2.y))
    def __str__(self):
        return '(' + str(self.time) + ', '+ str(self.location_1) +', '+ str(self.location_2) + ')'

class Constraints(object):
    def __init__(self):
        self.vertex_constraints = set()
        self.edge_constraints = set()

    def add_constraint(self, other):
        self.vertex_constraints |= other.vertex_constraints
        self.edge_constraints |= other.edge_constraints

    def __str__(self):
        return "VC: " + str([str(vc) for vc in self.vertex_constraints])  + \
            "EC: " + str([str(ec) for ec in self.edge_constraints])

class Environment(object):
    def __init__(self, dimension, agents, obstacles, graphs=None):
        self.dimension = dimension
        self.obstacles = obstacles

        self.agents = agents
        self.agent_dict = {}

        self.constraints = Constraints()
        self.constraint_dict = {}

        # Hỗ trợ Graph mode
        self.graphs = graphs # agent_name -> graph
        self.current_agent = None
        self.point_coords = {}
        self.coord_to_name = {}

        self.make_agent_dict()

        self.a_star = AStar(self)

    def get_neighbors(self, state):
        neighbors = []

        # Nếu dùng Graph (Đồ thị các điểm an toàn)
        current_graph = self.graphs.get(self.current_agent) if self.graphs else None

        if current_graph:
            # Lấy tên điểm hiện tại dựa trên tọa độ để tra cứu trong graph
            curr_name = self.coord_to_name.get((state.location.x, state.location.y))
            if curr_name and curr_name in current_graph:
                for neighbor_name in current_graph[curr_name]:
                    new_loc = self.point_coords.get(neighbor_name)
                    if not new_loc:
                        continue
                    # Tính toán hướng di chuyển (độ) để xác định Footprint hình chữ nhật
                    angle = np.degrees(np.arctan2(new_loc.y - state.location.y, new_loc.x - state.location.x))
                    n = State(state.time + 1, new_loc, direction=angle)
                    if self.state_valid(n) and self.transition_valid(state, n):
                        neighbors.append(n)
            # Luôn có option đứng đợi
            wait_state = State(state.time + 1, state.location, direction=state.direction)
            if self.state_valid(wait_state):
                neighbors.append(wait_state)
        else:
            # Chế độ Grid truyền thống (giữ nguyên logic cũ nếu cần)
            dx = [1, 0, -1, 0]; dy = [0, 1, 0, -1]
            for i in range(4):
                new_loc = Location(state.location.x + dx[i], state.location.y + dy[i])
                n = State(state.time + 1, new_loc, i)
                if self.state_valid(n) and self.transition_valid(state, n):
                    neighbors.append(n)
            neighbors.append(State(state.time + 1, state.location, state.direction))

        return neighbors

    def is_point_in_rect(self, px, py, cx, cy, angle_deg, L_front, L_back, W_half):
        """Kiểm tra một điểm có nằm trong hình chữ nhật xoay (OBB) đã cộng lề an toàn không"""
        theta = np.radians(angle_deg)
        cos_t = np.cos(-theta)
        sin_t = np.sin(-theta)
        dx, dy = px - cx, py - cy
        # Chuyển tọa độ về hệ trục địa phương của AGV
        local_x = dx * cos_t - dy * sin_t
        local_y = dx * sin_t + dy * cos_t
        return (L_back - SAFETY_MARGIN) <= local_x <= (L_front + SAFETY_MARGIN) and \
               (-W_half - SAFETY_MARGIN) <= local_y <= (W_half + SAFETY_MARGIN)

    def get_occupied_cells(self, state, next_state=None):
        """
        Trả về danh sách các nút bị chiếm dụng.
        Nếu có next_state, sẽ khóa cả tài nguyên của lộ trình di chuyển.
        """
        occupied = set()
        
        # 1. Lấy footprint hình chữ nhật tại vị trí hiện tại
        current_footprint = self._get_footprint_at_state(state)
        for loc in current_footprint:
            occupied.add((loc.x, loc.y))

        # 2. Nếu đang di chuyển (có next_state), khóa thêm footprint tại điểm đích đến
        if next_state:
            next_footprint = self._get_footprint_at_state(next_state)
            for loc in next_footprint:
                occupied.add((loc.x, loc.y))
                
        # Chuyển đổi ngược lại thành danh sách Location objects
        return [Location(pos[0], pos[1]) for pos in occupied]

    def _get_footprint_at_state(self, state):
        """Hàm phụ trợ tính toán footprint từ một state đơn lẻ"""
        footprint = [state.location]
        for name, pos_obj in self.point_coords.items():
            if self.is_point_in_rect(pos_obj.x, pos_obj.y, state.location.x, state.location.y, 
                                     state.direction, AGENT_L_FRONT, AGENT_L_BACK, AGENT_W_HALF):
                footprint.append(pos_obj)
        return footprint

    def get_first_conflict(self, solution):
        max_t = max([len(plan) for plan in solution.values()])
        
        # Thu thập tất cả các xung đột để phân loại
        all_conflicts = []

        # 1. Kiểm tra Vertex Conflicts
        for t in range(max_t):
            for agent_1, agent_2 in combinations(solution.keys(), 2):
                state_1 = self.get_state(agent_1, solution, t)
                state_2 = self.get_state(agent_2, solution, t)
                if self.check_collision(state_1, state_2):

                    result = Conflict()
                    result.time = t
                    result.type = Conflict.VERTEX
                    result.location_1 = state_1.location
                    result.agent_1 = agent_1
                    result.agent_2 = agent_2
                    all_conflicts.append(result)

    def check_collision(self, state_1, state_2):
        """Kiểm tra va chạm giữa 2 AGV sử dụng OBB và có tính đến Safety Margin"""
        dist = np.sqrt((state_1.location.x - state_2.location.x)**2 + (state_1.location.y - state_2.location.y)**2)
        
        # Ngưỡng an toàn nhanh (tổng đường chéo + margin)
        if dist > 4000: return False 

        # Kiểm tra các góc của AGV này có nằm trong AGV kia không
        # Sử dụng kích thước đã bao gồm Safety Margin
        L_F = AGENT_L_FRONT + SAFETY_MARGIN
        L_B = AGENT_L_BACK - SAFETY_MARGIN
        W_H = AGENT_W_HALF + SAFETY_MARGIN

        for s_curr, s_other in [(state_1, state_2), (state_2, state_1)]:
            for dx, dy in [(L_F, W_H), (L_F, -W_H), (L_B, W_H), (L_B, -W_H)]:
                rad = np.radians(s_curr.direction)
                px = s_curr.location.x + dx * np.cos(rad) - dy * np.sin(rad)
                py = s_curr.location.y + dx * np.sin(rad) + dy * np.cos(rad)
                if self.is_point_in_rect(px, py, s_other.location.x, s_other.location.y, 
                                         s_other.direction, AGENT_L_FRONT, AGENT_L_BACK, AGENT_W_HALF):
                    return True
        
        # Bổ sung kiểm tra tâm đối phương (tránh trường hợp xe quá nhỏ lọt vào giữa xe lớn)
        if self.is_point_in_rect(state_1.location.x, state_1.location.y, 
                                 state_2.location.x, state_2.location.y, 
                                 state_2.direction, AGENT_L_FRONT, AGENT_L_BACK, AGENT_W_HALF):
            return True

        return False

    def count_all_conflicts(self, solution):
        """Đếm tổng số xung đột trong một giải pháp (dùng cho Bypass strategy)"""
        count = 0
        max_t = max([len(plan) for plan in solution.values()])
        for t in range(max_t):
            for agent_1, agent_2 in combinations(solution.keys(), 2):
                s1 = self.get_state(agent_1, solution, t)
                s2 = self.get_state(agent_2, solution, t)
                if s1.is_equal_except_time(s2):
                    count += 1
                
                s1_next = self.get_state(agent_1, solution, t+1)
                s2_next = self.get_state(agent_2, solution, t+1)
                if s1.is_equal_except_time(s2_next) and s1_next.is_equal_except_time(s2):
                    count += 1
        return count

    def create_constraints_from_conflict(self, conflict):
        constraint_dict = {}
        if conflict.type == Conflict.VERTEX:
            v_constraint = VertexConstraint(conflict.time, conflict.location_1)
            constraint = Constraints()
            constraint.vertex_constraints |= {v_constraint}
            constraint_dict[conflict.agent_1] = constraint
            constraint_dict[conflict.agent_2] = constraint

        elif conflict.type == Conflict.EDGE:
            constraint1 = Constraints()
            constraint2 = Constraints()

            e_constraint1 = EdgeConstraint(conflict.time, conflict.location_1, conflict.location_2)
            e_constraint2 = EdgeConstraint(conflict.time, conflict.location_2, conflict.location_1)

            constraint1.edge_constraints |= {e_constraint1}
            constraint2.edge_constraints |= {e_constraint2}

            constraint_dict[conflict.agent_1] = constraint1
            constraint_dict[conflict.agent_2] = constraint2

        return constraint_dict

    def get_state(self, agent_name, solution, t):
        if t < len(solution[agent_name]):
            return solution[agent_name][t]
        else:
            return solution[agent_name][-1]

    def state_valid(self, state):
        # Tăng giới hạn thời gian (số bước) để hỗ trợ các chặng đường dài trong hệ tọa độ mm
        if state.time > 2000: return False

        if self.graphs:
            # Ở đây, 'state' là trạng thái dự kiến tiếp theo. 
            # Ta kiểm tra footprint của nó có dính VertexConstraint nào không.
            footprint = self.get_occupied_cells(state) 
            for cell in footprint:
                if VertexConstraint(state.time, cell) in self.constraints.vertex_constraints:
                    return False
            return True
            
        occupied = self.get_occupied_cells(state)
        for cell in occupied:
            if cell.x < 0 or cell.x >= self.dimension[0] or \
               cell.y < 0 or cell.y >= self.dimension[1]:
                return False
            if (cell.x, cell.y) in self.obstacles:
                return False
            if VertexConstraint(state.time, cell) in self.constraints.vertex_constraints:
                return False
        return True

    def transition_valid(self, state_1, state_2):
        return EdgeConstraint(state_1.time, state_1.location, state_2.location) not in self.constraints.edge_constraints

    def is_solution(self, agent_name):
        pass

    def admissible_heuristic(self, state, agent_name):
        goal = self.agent_dict[agent_name]["goal"]
        # Tính khoảng cách Euclid thực tế (đơn vị mm)
        dist = np.sqrt((state.location.x - goal.location.x)**2 + (state.location.y - goal.location.y)**2)
        
        # Chuyển đổi khoảng cách mm sang đơn vị "bước thời gian" ước tính.
        # Giả sử vận tốc trung bình AGV là 1000mm/s và mỗi bước t = 1s.
        # Việc có Heuristic giúp AGV ưu tiên đứng yên hoặc tiến về đích thay vì đi giật lùi vô nghĩa.
        return dist / 1000.0


    def is_at_goal(self, state, agent_name):
        goal_state = self.agent_dict[agent_name]["goal"]
        
        # Chỉ kiểm tra vị trí (x, y), không kiểm tra state.direction
        if not state.is_equal_except_time(goal_state):
            return False
        
        # Tối ưu hóa kiểm tra nhường đường: Sử dụng O(1) lookup thay vì lặp O(n)
        for t_future in range(state.time + 1, state.time + 201):
            if VertexConstraint(t_future, state.location) in self.constraints.vertex_constraints:
                return False
        return True

    def make_agent_dict(self):
        for agent in self.agents:
            start_state = State(0, Location(agent['start'][0], agent['start'][1]), direction=0)
            # Sửa dòng dưới đây: 
            # Thay vì hướng 0, ta có thể để một giá trị đặc biệt hoặc xử lý trong is_at_goal
            goal_state = State(0, Location(agent['goal'][0], agent['goal'][1]), direction=None) 
            self.agent_dict.update({agent['name']:{'start':start_state, 'goal':goal_state}})

    def compute_solution(self, agent_name, solution):
        """Tính toán lại đường đi chỉ cho 1 agent cụ thể"""
        self.current_agent = agent_name
        self.constraints = self.constraint_dict.setdefault(agent_name, Constraints())
        local_solution = self.a_star.search(agent_name)
        if not local_solution:
            return False
        solution.update({agent_name: local_solution})
        return True

    def compute_solution_cost(self, solution):
        return sum([len(path) for path in solution.values()])

class HighLevelNode(object):
    def __init__(self):
        self.solution = {}
        self.constraint_dict = {}
        self.cost = 0

    def __eq__(self, other):
        if not isinstance(other, type(self)): return NotImplemented
        return self.solution == other.solution and self.cost == other.cost

    def __hash__(self):
        return hash((self.cost))

    def __lt__(self, other):
        return self.cost < other.cost

class CBS(object):
    def __init__(self, environment):
        self.env = environment
        self.open_set = set()
        self.closed_set = set()

    def _resolve_goal_conflicts(self, sorted_agents):
        """
        Kiểm tra và xử lý trường hợp nhiều AGV có cùng đích đến.
        Nếu trùng, AGV ưu tiên thấp hơn sẽ chọn 1 điểm lân cận trống làm đích.
        """
        occupied_goals = {} # location_tuple -> agent_name
        
        for agent_name in sorted_agents:
            goal_loc = self.env.agent_dict[agent_name]['goal'].location
            goal_tuple = (goal_loc.x, goal_loc.y)
            
            if goal_tuple in occupied_goals:
                other_agent = occupied_goals[goal_tuple]
                print(f" [!] Cảnh báo: {agent_name} trùng đích với {other_agent} tại {goal_loc}. Đang tìm điểm đỗ thay thế...")
                
                # Tìm trong graph các điểm lân cận của đích cũ
                curr_graph = self.env.graphs.get(agent_name) if self.env.graphs else None
                goal_node_name = self.env.coord_to_name.get(goal_tuple)
                
                if curr_graph and goal_node_name in curr_graph:
                    neighbors = curr_graph[goal_node_name]
                    found_new_goal = False
                    for n_name in neighbors:
                        n_loc = self.env.point_coords[n_name]
                        if (n_loc.x, n_loc.y) not in occupied_goals:
                            # Cập nhật đích mới cho AGV này
                            self.env.agent_dict[agent_name]['goal'].location = n_loc
                            occupied_goals[(n_loc.x, n_loc.y)] = agent_name
                            print(f"     -> Đã chuyển đích của {agent_name} sang {n_name} {n_loc}")
                            found_new_goal = True
                            break
                    if not found_new_goal:
                        occupied_goals[goal_tuple] = agent_name # Giữ nguyên nếu không còn chỗ
                else:
                    occupied_goals[goal_tuple] = agent_name
            else:
                occupied_goals[goal_tuple] = agent_name

    def search(self):
        """Lập kế hoạch ưu tiên với cơ chế bảo vệ va chạm tuyệt đối"""
        final_solution = {}
        self.env.constraint_dict = {}
        
        # Sắp xếp agent: con nào ở xa đích hơn ưu tiên lập kế hoạch trước Conflicts
        # Điều này giúp các con ở sâu trong kho tìm được lối ra trước khi bị con khác chặn
        print(f"Đang bắt đầu lập kế hoạch cho {len(self.env.agent_dict)} AGV...")
        sorted_agents = sorted(self.env.agent_dict.keys(), 
                       key=lambda a: self.env.admissible_heuristic(self.env.agent_dict[a]['start'], a), 
                       reverse=True)

        # BƯỚC 0: Xử lý trùng lặp đích đến
        self._resolve_goal_conflicts(sorted_agents)

        for agent_name in sorted_agents:
            print(f" -> Đang tìm đường cho {agent_name}...", end=" ", flush=True)
            # Tìm đường cho agent hiện tại dựa trên các ràng buộc từ các con trước đó
            self.env.current_agent = agent_name
            self.env.constraints = self.env.constraint_dict.setdefault(agent_name, Constraints())
            
            # CẢI TIẾN: Chặn các AGV chưa di chuyển tại vị trí xuất phát của chúng trong suốt thời gian đợi
            for other_name in sorted_agents:
                if other_name not in final_solution and other_name != agent_name:
                    unplanned_start = self.env.agent_dict[other_name]['start'].location
                    # Chỉ chặn tại thời điểm t=0 để tránh va chạm lúc khởi đầu.
                    # Điều này cho phép AGV4 đi qua vị trí của AGV3 nếu AGV3 đã di chuyển.
                    self.env.constraints.vertex_constraints.add(VertexConstraint(0, unplanned_start))

            local_path = self.env.a_star.search(agent_name)
            if not local_path:
                print(f"Thất bại!")
                local_path = [self.env.agent_dict[agent_name]['start']]
            else:
                print(f"Xong (Độ dài: {len(local_path)})")

            final_solution[agent_name] = local_path
            
            # Biến lộ trình của AGV này thành vật cản cho các AGV sau
            for other_agent in sorted_agents:
                if other_agent == agent_name: continue
                
                other_constraints = self.env.constraint_dict.setdefault(other_agent, Constraints())
                
                # Trong file cbs.py, tìm đoạn: for t, state in enumerate(local_path):
                for t in range(len(local_path)):
                    state = local_path[t]
                    next_state = local_path[t+1] if t < len(local_path) - 1 else None
                    
                    # Lấy tất cả các ô bị chiếm dụng (bao gồm điểm hiện tại và điểm sắp tới nếu đang di chuyển)
                    #
                    combined_footprint = self.env.get_occupied_cells(state, next_state)
                    
                    for cell in combined_footprint:
                        other_constraints.vertex_constraints.add(VertexConstraint(state.time, cell))
                        # Nếu đang di chuyển, khóa luôn ô đó ở thời điểm t+1 để đảm bảo không ai nhảy vào
                        # CẢI TIẾN: Thêm một khoảng đệm thời gian nhỏ (ví dụ 1-2 đơn vị) để AGV nhường nhau an toàn hơn
                        for buffer_t in range(1, 2):
                            other_constraints.vertex_constraints.add(VertexConstraint(state.time + buffer_t, cell))

                # Khóa vị trí đích: Chỉ nên khóa khi AGV thực sự đã đến đích
                last_state = local_path[-1]
                # Nếu AGV đứng yên (độ dài path = 1), không cần khóa vĩnh viễn vị trí xuất phát của nó
                if len(local_path) > 1:
                    final_footprint = self.env.get_occupied_cells(last_state)
                    for future_t in range(last_state.time + 1, last_state.time + 200): 
                        for cell in final_footprint:
                            other_constraints.vertex_constraints.add(VertexConstraint(future_t, cell))

        # BƯỚC 2: Tối ưu hóa việc đứng chờ (Xóa bỏ hiện tượng nhảy múa A -> B -> A)
        final_solution = self.toi_uu_cho_doi(final_solution)

        # BƯỚC 3: Rút gọn các điểm trung gian trên đường thẳng để di chuyển mượt mà
        final_solution = self.rut_gon_duong_thanh(final_solution)

        return self.generate_plan(final_solution)

    def rut_gon_duong_thanh(self, solution):
        """
        Loại bỏ các điểm nút trung gian nằm trên một đường thẳng nếu AGV không dừng lại.
        Giúp AGV di chuyển liên tục từ điểm đầu đến điểm cuối của đoạn thẳng.
        """
        pruned_solution = {}
        for agent_name, path in solution.items():
            if len(path) < 3:
                pruned_solution[agent_name] = path
                continue

            new_path = [path[0]]
            for i in range(1, len(path) - 1):
                prev = path[i-1]
                curr = path[i]
                nxt = path[i+1]

                # 1. Kiểm tra xem 3 điểm có thẳng hàng không (Sử dụng tích chéo với ngưỡng sai số mm)
                # Tích chéo: (y2-y1)(x3-x2) - (y3-y2)(x2-x1). Ngưỡng 100,000 là khoảng lệch rất nhỏ so với tọa độ mm.
                cross_product = (curr.location.y - prev.location.y) * (nxt.location.x - curr.location.x) - \
                                (nxt.location.y - curr.location.y) * (curr.location.x - prev.location.x)
                is_collinear = abs(cross_product) < 100000

                # 2. Kiểm tra xem AGV có đứng chờ tại điểm này không
                # Nếu vị trí không đổi so với điểm trước hoặc sau, nghĩa là đang chờ -> Phải giữ lại
                is_waiting = (curr.location == prev.location) or (curr.location == nxt.location)

                # 3. Kiểm tra hướng di chuyển để tránh trường hợp quay đầu (dot product > 0)
                dot_product = (curr.location.x - prev.location.x) * (nxt.location.x - curr.location.x) + \
                              (curr.location.y - prev.location.y) * (nxt.location.y - curr.location.y)
                is_same_direction = dot_product > 0

                # Nếu thẳng hàng, cùng hướng và không đứng chờ, có thể rút gọn để di chuyển mượt mà.
                # Bỏ qua kiểm tra tỷ lệ khoảng cách/thời gian để AGV đi thẳng liên tục giữa các điểm chính.
                if is_collinear and is_same_direction and not is_waiting:
                    continue # Bỏ qua điểm trung gian này
                new_path.append(curr)
            
            new_path.append(path[-1])
            pruned_solution[agent_name] = new_path
        return pruned_solution

    def toi_uu_cho_doi(self, solution):
        """Hậu xử lý để AGV đứng im thay vì di chuyển qua lại khi chờ đợi"""
        optimized_solution = deepcopy(solution)
        agents = list(optimized_solution.keys())
        
        for _ in range(2): # Lặp lại để gộp các chuỗi nhảy liên tiếp
            any_change = False
            for agent_name in agents:
                path = optimized_solution[agent_name]
                if len(path) < 3: continue
                
                new_path = [path[0]]
                for t in range(1, len(path) - 1):
                    curr = path[t]
                    prev = path[t-1]
                    nxt = path[t+1]
                    
                    # Phát hiện nhảy múa: quay lại điểm cũ ngay lập tức
                    if prev.location == nxt.location and curr.location != prev.location:
                        # Giả định nếu đứng im tại vị trí cũ (prev) ở thời điểm t
                        test_state = State(t, prev.location, direction=prev.direction)
                        safe = True
                        for other in agents:
                            if other == agent_name: continue
                            if self.env.check_collision(test_state, self.env.get_state(other, optimized_solution, t)):
                                safe = False; break
                        
                        if safe:
                            new_path.append(test_state)
                            any_change = True
                            continue
                    new_path.append(curr)
                new_path.append(path[-1])
                optimized_solution[agent_name] = new_path
            if not any_change: break
        return optimized_solution

    def generate_plan(self, solution):
        plan = {}
        for agent, path in solution.items():
            path_dict_list = []
            for state in path:
                point_name = self.env.coord_to_name.get((state.location.x, state.location.y), "Unknown")
                path_dict_list.append({
                    't': state.time,
                    'x': state.location.x,
                    'y': state.location.y,
                    'd': state.direction,
                    'name': point_name
                })
            plan[agent] = path_dict_list
        return plan



def main(data_agv, danh_sach_diem, danh_sach_duong):
    # Chuyển đổi danh_sach_diem sang mapping PointName -> Location object
    point_coords = {name: Location(val[0], val[1]) for name, val in danh_sach_diem.items()}
    coord_to_name = {(loc.x, loc.y): name for name, loc in point_coords.items()}

    # Chuẩn bị danh sách agents từ data_agv của load_graph
    agents = []
    for agv_id, info in data_agv.items():
        if info["start"] != "":
            if info["goal"] == "":
                point_coords[info["goal"]] = point_coords[info["start"]]
            agents.append({
                    "name": agv_id,
                    "start": [point_coords[info["start"]].x, point_coords[info["start"]].y],
                    "goal": [point_coords[info["goal"]].x, point_coords[info["goal"]].y]
                })

        

    # Tự động tính toán kích thước bản đồ dựa trên tọa độ các điểm
    max_x = max(loc.x for loc in point_coords.values()) + 100
    max_y = max(loc.y for loc in point_coords.values()) + 100
    dimension = [max_x, max_y]
    obstacles = [] # Trong chế độ Graph, các điểm nút được coi là an toàn

    # Sử dụng đồ thị đầy đủ cho tất cả AGV để giữ lại các điểm trung gian làm vị trí tránh nhau
    full_graph = tao_graph(danh_sach_duong)
    agent_graphs = {agv_id: full_graph for agv_id in data_agv}

    # Kiểm tra tính hợp lệ của điểm bắt đầu trên đồ thị riêng của từng AGV
    for agent in agents:
        curr_name = coord_to_name.get((agent["start"][0], agent["start"][1]))
        agent_graph = agent_graphs.get(agent["name"])
        if not curr_name or not agent_graph or curr_name not in agent_graph:
            print(f"CẢNH BÁO: Điểm bắt đầu của {agent['name']} ({curr_name}) không có trong graph tối ưu!")

    env = Environment(dimension, agents, obstacles, graphs=agent_graphs)
    env.point_coords = point_coords
    env.coord_to_name = coord_to_name

    # Searching
    cbs = CBS(env)
    solution = cbs.search()
    if not solution:
        print(" Solution not found" )
        return

    # Write to output file
    output = dict()
    output["schedule"] = solution
    output["cost"] = env.compute_solution_cost(solution)
    # print(f"Giải pháp tìm được với chi phí {output}. Đang ghi vào file...")
    # with open(output_file_path, 'w') as f:
    #     json.dump(output, f, indent=4)
    return output


if __name__ == "__main__":
    OUTPUT_FILE = 'output_graph.json'
    from load_graph import danh_sach_diem, data_agv, danh_sach_duong

    main(data_agv, danh_sach_diem, danh_sach_duong)
    # get_occupied_cells for t, state in enumerate(local_path): state_valid make_agent_dict is_at_goal 