#!/usr/bin/env python3
import json
import matplotlib
# matplotlib.use("Agg")
from matplotlib.patches import Circle, Rectangle, Arrow
from matplotlib.collections import PatchCollection
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import animation
import matplotlib.animation as manimation
import math
import random
import load_graph

Colors = ['orange', 'blue', 'green', 'purple', 'cyan', 'magenta']


class Animation:
  def __init__(self, map, schedule, danh_sach_diem=None, danh_sach_duong=None):
    self.map = map
    self.schedule = schedule
    self.danh_sach_diem = danh_sach_diem
    self.danh_sach_duong = danh_sach_duong
    self.combined_schedule = {}
    self.combined_schedule.update(self.schedule["schedule"])
    self.input_new_generated = False

    # Tính toán giới hạn hiển thị tự động từ vị trí thực tế của các agent (hệ tọa độ mm)
    all_coords = []
    for d in map["agents"]:
        all_coords.append(d["start"])
        all_coords.append(d["goal"])
    all_coords = np.array(all_coords)
    
    padding = 10000 # mm (Tăng padding để thu nhỏ tỷ lệ bản đồ, nhìn rộng hơn)
    xmin = np.min(all_coords[:, 0]) - padding
    xmax = np.max(all_coords[:, 0]) + padding
    ymin = np.min(all_coords[:, 1]) - padding
    ymax = np.max(all_coords[:, 1]) + padding

    aspect = (xmax - xmin) / (ymax - ymin)

    self.fig = plt.figure(frameon=False, figsize=(10 * aspect, 10)) # Tăng kích thước khung hình
    self.ax = self.fig.add_subplot(111, aspect='equal')
    self.fig.subplots_adjust(left=0,right=1,bottom=0,top=1, wspace=None, hspace=None)
    # self.ax.set_frame_on(False)

    self.patches = []
    self.artists = []
    self.agents = dict()
    self.agent_names = dict()

    # Tạo lookup table cho các cạnh để truy xuất nhanh loại đường (đường thẳng hay cong)
    self.edge_lookup = {}
    if self.danh_sach_duong:
        for edge_id, info in self.danh_sach_duong.items():
            u, v = info[0]
            # Sử dụng tuple đã sắp xếp để tra cứu không phân biệt hướng (nếu là đường 2 chiều)
            self.edge_lookup[tuple(sorted((u, v)))] = info

    # Vẽ sơ đồ đường đi (Graph Edges) làm nền
    if self.danh_sach_diem and self.danh_sach_duong:
        for edge_id, info in self.danh_sach_duong.items():
            p1_name, p2_name = info[0]
            type_path = info[1]
            
            if p1_name not in self.danh_sach_diem or p2_name not in self.danh_sach_diem:
                continue
                
            p1 = np.array([self.danh_sach_diem[p1_name][0], self.danh_sach_diem[p1_name][1]])
            p2 = np.array([self.danh_sach_diem[p2_name][0], self.danh_sach_diem[p2_name][1]])
            
            if type_path == "curve" and len(info) > 2:
                # Vẽ đường cong Bezier bậc 2 qua 3 điểm
                ctrl_name = info[2]
                if ctrl_name in self.danh_sach_diem:
                    p_ctrl = np.array([self.danh_sach_diem[ctrl_name][0], self.danh_sach_diem[ctrl_name][1]])
                    
                    # Tính toán các điểm trên đường cong
                    t = np.linspace(0, 1, 20)
                    # Công thức: (1-t)^2 * P0 + 2*(1-t)*t * P1 + t^2 * P2
                    bezier_points = (
                        (1 - t)[:, None]**2 * p1 + 
                        2 * (1 - t)[:, None] * t[:, None] * p_ctrl + 
                        t[:, None]**2 * p2
                    )
                    self.ax.plot(bezier_points[:, 0], bezier_points[:, 1], color='lightgray', linestyle='--', linewidth=1, zorder=0)
                else:
                    # Nếu không tìm thấy điểm control, vẽ đường thẳng thay thế
                    self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color='lightgray', linestyle='--', linewidth=1, zorder=0)
            else:
                # Vẽ đường thẳng mặc định
                self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color='lightgray', linestyle='--', linewidth=1, zorder=0)

        # Vẽ các điểm nút (Nodes)
        for name, pos in self.danh_sach_diem.items():
            if "-" not in name: # Chỉ vẽ các điểm chính, bỏ qua điểm control của curve nếu tên có dấu gạch
                self.ax.scatter(pos[0], pos[1], c='black', s=10, alpha=0.3, zorder=1)

    # Vẽ lộ trình thực tế theo kế hoạch (đã rút gọn) của từng AGV
    for i, agent_def in enumerate(map["agents"]):
      name = agent_def["name"]
      if name in self.combined_schedule:
        color = Colors[i % len(Colors)]
        path = self.combined_schedule[name]
        px = [step['x'] for step in path]
        py = [step['y'] for step in path]
        # Vẽ đường nối nét đứt thể hiện lộ trình trực tiếp
        self.ax.plot(px, py, color=color, alpha=0.4, linewidth=2, linestyle='--', zorder=2)
        # Vẽ các điểm mốc (waypoints) mà AGV sẽ đi qua
        self.ax.scatter(px, py, color=color, s=50, marker='o', edgecolors='white', alpha=0.8, zorder=3)

    # self.ax.relim()
    plt.xlim(xmin, xmax)
    plt.ylim(ymin, ymax)
    # self.ax.set_xticks([])
    # self.ax.set_yticks([])
    # plt.axis('off')
    # self.ax.axis('tight')
    # self.ax.axis('off')

    self.patches.append(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, facecolor='none', edgecolor='red'))
    for o in map["map"]["obstacles"]:
      x, y = o[0], o[1]
      self.patches.append(Rectangle((x - 0.5, y - 0.5), 1, 1, facecolor='red', edgecolor='red'))

    # create agents:
    self.T = 0
    # draw goals first
    for i, d in enumerate(map["agents"]):
      color = Colors[i % len(Colors)]
      # Giảm kích thước đích xuống (ví dụ: 1000mm)
      self.patches.append(Rectangle((d["goal"][0] - 500, d["goal"][1] - 500), 1000, 1000, facecolor=color, edgecolor='black', alpha=0.5))
    for i, d in enumerate(map["agents"]):
      name = d["name"]
      color = Colors[i % len(Colors)]
      # Kích thước vùng an toàn mới: 2200mm x 900mm
      # Lưu ý: Rectangle vẽ từ góc dưới trái, ta cần offset để tâm trùng với tọa độ điểm
      self.agents[name] = Rectangle((0, 0), 2200, 900, facecolor=color, edgecolor='black', zorder=3, alpha=0.8)
      self.agents[name].original_face_color = color
      self.patches.append(self.agents[name])
      self.T = max(self.T, schedule["schedule"][name][-1]["t"])
      self.agent_names[name] = self.ax.text(d["start"][0], d["start"][1], name.replace('agent', ''))
      self.agent_names[name].set_horizontalalignment('center')
      self.agent_names[name].set_verticalalignment('center')
      self.artists.append(self.agent_names[name])

    # self.ax.set_axis_off()
    # self.fig.axes[0].set_visible(False)
    # self.fig.axes.get_yaxis().set_visible(False)

    # self.fig.tight_layout()

    self.anim = animation.FuncAnimation(self.fig, self.animate_func,
                               init_func=self.init_func,
                               frames=int(self.T+1) * 10,
                               interval=100,
                               blit=True)

  def save(self, file_name, speed):
    self.anim.save(
      file_name,
      "ffmpeg",
      fps=10 * speed,
      dpi=200),
      # savefig_kwargs={"pad_inches": 0, "bbox_inches": "tight"})

  def show(self):
    plt.show()

  def generate_random_goal(self):
    dimensions = self.map["map"]["dimensions"]
    obstacles = self.map["map"]["obstacles"]
    while True:
      x = random.randint(0, dimensions[0] - 1)
      y = random.randint(0, dimensions[1] - 1)
      if [x, y] not in obstacles:
        return [x, y]

  def init_func(self):
    for p in self.patches:
      self.ax.add_patch(p)
    for a in self.artists:
      self.ax.add_artist(a)
    return self.patches + self.artists

  def animate_func(self, i):
    t_curr = i / 10

    # Kiểm tra xem có AGV nào đến đích đầu tiên không để tạo input_new.json
    if not self.input_new_generated:
      for agent_def in self.map["agents"]:
        name = agent_def["name"]
        goal = np.array(agent_def["goal"])
        pos, _ = self.getStateWithHeading(t_curr, self.combined_schedule[name])
        
        # Kiểm tra nếu AGV đã ở vị trí đích và thời gian đã đạt đến thời điểm kết thúc kế hoạch
        if np.allclose(pos, goal, atol=0.01) and t_curr >= self.combined_schedule[name][-1]["t"]:
          print(f"Agent {name} reached goal at t={t_curr}. Creating input_new.json...")
          new_input = {
              "agents": [],
              "map": self.map["map"]
          }
          for a_def in self.map["agents"]:
              a_name = a_def["name"]
              a_pos, _ = self.getStateWithHeading(t_curr, self.combined_schedule[a_name])
              
              new_a_def = {
                  "name": a_name,
                  "start": [int(round(a_pos[0])), int(round(a_pos[1]))],
                  "goal": self.generate_random_goal() if a_name == name else a_def["goal"]
              }
              new_input["agents"].append(new_a_def)
          
          with open('input_new.json', 'w') as f:
              json.dump(new_input, f, indent=4)
          self.input_new_generated = True
          break

    for agent_name, agent in self.combined_schedule.items():
      pos, angle = self.getStateWithHeading(t_curr, agent)
      
      # Cập nhật vị trí và góc xoay cho Rectangle (xoay quanh tâm)
      # AGV center to edges: Front +1250, Back -950, Side +/- 450
      L_back, W_half = -950, -450
      rad = np.radians(angle)
      # Tính toán tọa độ góc dưới-trái sau khi xoay quanh tâm AGV
      corner_x = pos[0] + L_back * np.cos(rad) - W_half * np.sin(rad)
      corner_y = pos[1] + L_back * np.sin(rad) + W_half * np.cos(rad)
      
      self.agents[agent_name].set_xy((corner_x, corner_y))
      self.agents[agent_name].angle = angle
      self.agent_names[agent_name].set_position((pos[0], pos[1]))

    # reset all colors
    for _,agent in self.agents.items():
      agent.set_facecolor(agent.original_face_color)

    # check drive-drive collisions
    agents_array = [agent for _,agent in self.agents.items()]
    for i in range(0, len(agents_array)):
      for j in range(i+1, len(agents_array)):
        d1 = agents_array[i]
        d2 = agents_array[j]
        # Kiểm tra khoảng cách giữa 2 tâm xe (Pivot points)
        p1 = self.agent_names[list(self.agents.keys())[i]].get_position()
        p2 = self.agent_names[list(self.agents.keys())[j]].get_position()
        
        # Ngưỡng cảnh báo dựa trên tổng chiều dài vùng an toàn (~2200mm)
        if np.linalg.norm(np.array(p1) - np.array(p2)) < 2200:
          d1.set_facecolor('red')
          d2.set_facecolor('red')
          print("COLLISION! (agent-agent) ({}, {})".format(i, j))

    return self.patches + self.artists

  def getStateWithHeading(self, t, d):
    """Trả về (vị trí_numpy, góc_xoay_độ)"""
    idx = 0
    while idx < len(d) and d[idx]["t"] < t:
        idx += 1
      
    if idx == 0:
        return np.array([float(d[0]["x"]), float(d[0]["y"])]), d[0].get("d", 0) # Lấy hướng khởi tạo
    elif idx < len(d):
      posLast = np.array([float(d[idx-1]["x"]), float(d[idx-1]["y"])])
      posNext = np.array([float(d[idx]["x"]), float(d[idx]["y"])])
      name_last = d[idx-1].get("name")
      name_next = d[idx].get("name")
    else:
        # Khi t vượt quá thời gian trong schedule (đã đến đích)
        # Trả về tọa độ đích và hướng của trạng thái cuối cùng trong danh sách
        return np.array([float(d[-1]["x"]), float(d[-1]["y"])]), d[-1].get("d", 0)
    
    dt = d[idx]["t"] - d[idx-1]["t"]
    t_interp = (t - d[idx-1]["t"]) / dt
    
    # Mặc định vector hướng là đường thẳng
    direction_vector = posNext - posLast
    
    # Kiểm tra xem đoạn đường giữa 2 node này có phải là đường cong Bezier không
    if name_last and name_next:
        edge_info = self.edge_lookup.get(tuple(sorted((name_last, name_next))))
        if edge_info and edge_info[1] == "curve" and len(edge_info) > 2:
            ctrl_name = edge_info[2]
            if ctrl_name in self.danh_sach_diem:
                # Tọa độ điểm control (đã được đổi sang mm trong load_graph)
                p_ctrl = np.array([self.danh_sach_diem[ctrl_name][0], self.danh_sach_diem[ctrl_name][1]])
                # Nội suy theo công thức Bezier bậc 2: (1-t)^2*P0 + 2*(1-t)*t*P1 + t^2*P2
                pos = (1 - t_interp)**2 * posLast + 2 * (1 - t_interp) * t_interp * p_ctrl + t_interp**2 * posNext
                # Vector tiếp tuyến (đạo hàm): V(t) = 2(1-t)(P1-P0) + 2t(P2-P1)
                direction_vector = 2 * (1 - t_interp) * (p_ctrl - posLast) + 2 * t_interp * (posNext - p_ctrl)
                angle = np.degrees(np.arctan2(direction_vector[1], direction_vector[0]))
                return pos, angle

    # Nội suy tuyến tính
    pos = (posNext - posLast) * t_interp + posLast
    angle = np.degrees(np.arctan2(direction_vector[1], direction_vector[0]))
    return pos, angle



if __name__ == "__main__":
  # Cấu hình các tham số đầu vào tại đây
  SCHEDULE_FILE = 'output_graph.json'   # Kết quả từ cbs.py
  VIDEO_FILE = None               # Đường dẫn lưu video (vd: 'result.mp4'), hoặc để None để xem trực tiếp
  SPEED = 1                       # Hệ số tốc độ hiển thị (speedup-factor)

  # Lấy dữ liệu trực tiếp từ load_graph.py thay vì input.json
  from load_graph import danh_sach_diem, data_agv
  
  # Tái cấu trúc map_data từ dữ liệu graph để lớp Animation có thể xử lý
  coords = list(danh_sach_diem.values())
  
  map_data = {
      "map": {
          "dimensions": [1, 1], # Animation sẽ tự tính toán dựa trên tọa độ mm
          "obstacles": []
      },
      "agents": []
  }
  
  for agv_id, info in data_agv.items():
      map_data["agents"].append({
          "name": agv_id,
          "start": [danh_sach_diem[info["start"]][0], danh_sach_diem[info["start"]][1]],
          "goal": [danh_sach_diem[info["goal"]][0], danh_sach_diem[info["goal"]][1]]
      })

  with open(SCHEDULE_FILE) as states_file:
    schedule_data = json.load(states_file)

  anim_instance = Animation(map_data, schedule_data, danh_sach_diem=danh_sach_diem, danh_sach_duong=load_graph.danh_sach_duong)

  if VIDEO_FILE:
    anim_instance.save(VIDEO_FILE, SPEED)
  else:
    anim_instance.show()
# getStateWithHeading