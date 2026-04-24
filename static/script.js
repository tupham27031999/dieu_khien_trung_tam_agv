// --- Global Variables ---
// Biến lưu trạng thái lựa chọn của tất cả AGV
// Cấu trúc: { "agv1": { "chon_gia_hang": "A", "di_chuyen_khong_hang": "off", ... }, "agv2": ... }
let agvStates = {}; 
let currentAgv = null;
// Biến lưu trạng thái tạm thời đang chỉnh sửa (Draft)
// Khi người dùng thao tác, update vào draftState. Chỉ khi bấm Gửi mới update vào agvStates
let draftState = {}; 
let viewer = null; // Biến toàn cục cho OpenSeadragon
let isAddingMarker = false; // Trạng thái đang thêm marker
let mapMarkers = []; // Danh sách marker hiện tại trên bản đồ
let selectedMarkerIndex = -1; // Index của marker đang được chọn (-1 là chưa chọn)
let mapImgWidth = 1; // Chiều rộng ảnh bản đồ (pixel) dùng để quy đổi tọa độ
let agvOverlays = {}; // Lưu trữ các element AGV overlay: { "agv1": HTMLElement }
let dynamicPathSvg = null; // Layer SVG chứa đường đi động của các AGV
let allGraphPoints = []; // Lưu danh sách điểm để tính toán khoảng cách
let allGraphPaths = [];  // Lưu danh sách đường bao gồm cả loại đường (curve/none)
let isCreatingOccupiedRule = false;
let occSelectingType = null; // 'cond' (điểm xét) hoặc 'lock' (điểm khóa)
let currentOccCondition = [];
let currentOccLocked = [];
let tempLockStartPoint = null; // Điểm bắt đầu của một đường khóa đang được chọn
let occupiedRules = {}; // { "PointA,PointB": ["Lock1", "Lock2"] }

// --- Tab Handling ---
function openTab(evt, tabName) {
    var i, tabcontent, tablinks;
    
    // Ẩn tất cả nội dung tab
    tabcontent = document.getElementsByClassName("tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].classList.remove("active");
    }
    
    // Xóa class active khỏi tất cả button
    tablinks = document.getElementsByClassName("tab-btn");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].classList.remove("active");
    }
    
    // Hiển thị tab hiện tại và thêm class active cho button
    document.getElementById(tabName).classList.add("active");
    evt.currentTarget.classList.add("active");

    // Nếu mở tab View và viewer đã khởi tạo, hãy cập nhật lại (do thay đổi display: none -> block)
    if (tabName === 'viewTab' && viewer) {
        // Đợi một chút để CSS render xong kích thước div
        setTimeout(() => {
            viewer.viewport.goHome(true); // Reset zoom về mặc định
        }, 100);
    }
}

// --- Auto Update Info ---
function updateInfo() {
    fetch('/api/get_info')
        .then(response => response.json())
        .then(data => {
            const infoBox = document.getElementById('info-display');
            if (infoBox) {
                infoBox.value = data.info;
            }
            if (data.agv_states && viewer) {
                updateAgvDisplay(data.agv_states);
            }
        })
        .catch(error => console.error('Error fetching info:', error));
}

// Chạy cập nhật mỗi 1 giây (1000ms)
setInterval(updateInfo, 1000);

// --- AGV Settings & Logic ---

document.addEventListener('DOMContentLoaded', function() {
    // 1. Khởi tạo dữ liệu trạng thái cho tất cả AGV
    // Sử dụng dữ liệu từ server (SERVER_AGV_STATES) được truyền qua biến config
    // SERVER_AGV_STATES đã chứa sẵn cấu trúc bao gồm cả "danh_sach_ke_da_chon"
    if (typeof SERVER_AGV_STATES !== 'undefined' && Object.keys(SERVER_AGV_STATES).length > 0) {
        agvStates = SERVER_AGV_STATES;
    } else {
        // Fallback nếu không có dữ liệu server
        AGV_LIST.forEach(agvName => {
            agvStates[agvName] = {};
            for (const [key, item] of Object.entries(DEFAULT_OPTIONS)) {
                agvStates[agvName][key] = item.value;
            }
            agvStates[agvName]['danh_sach_ke_da_chon'] = [];
        });
    }

    // 1.1 Khởi tạo danh sách nhóm kệ (Combobox)
    if (typeof SHELF_GROUPS !== 'undefined') {
        const groupSelect = document.getElementById('marker-group-select');
        if (groupSelect) {
            SHELF_GROUPS.forEach(group => {
                const opt = document.createElement('option');
                opt.value = group;
                opt.innerText = `Hàng ${group}`;
                groupSelect.appendChild(opt);
            });
        }
    }

    // 2. Thiết lập AGV đầu tiên
    const agvSelect = document.getElementById('agv-select');
    if (agvSelect) {
        currentAgv = agvSelect.value;
        // Nếu combobox chọn giá hàng có giá trị mặc định, cần render ngay
        loadAgvState(currentAgv);
        
        // Lắng nghe sự kiện đổi AGV
        agvSelect.addEventListener('change', function() {
            // Trước khi đổi, lưu trạng thái của AGV hiện tại (nếu cần thiết, 
            // Ở logic mới: Nếu chưa bấm Gửi thì chuyển AGV sẽ mất thay đổi -> đúng yêu cầu)
            currentAgv = this.value;
            loadAgvState(currentAgv);
        });
    }

    // 3. Lắng nghe sự kiện thay đổi trên các ô input/select trong vùng Dynamic Options
    const dynamicInputs = document.querySelectorAll('.dynamic-options input, .dynamic-options select');
    dynamicInputs.forEach(input => {
        input.addEventListener('change', function() {
            if (!currentAgv) return;
            
            // Xác định giá trị
            let val;
            if (this.type === 'checkbox') {
                val = this.checked ? 'on' : 'off';
            } else {
                val = this.value;
            }
            
            // Cập nhật vào bản nháp (Draft)
            draftState[this.name] = val;
            console.log(`Draft updated for ${currentAgv}:`, draftState);

            // Nếu input thay đổi là "chon_gia_hang", render lại các nút bên phải
            if (this.name === 'chon_gia_hang') {
                renderShelfButtons(val);
            }
        });
    });

    // 4. Sự kiện nút Gửi danh sách đích
    const btnSend = document.getElementById('btn-send-list');
    if (btnSend) {
        btnSend.addEventListener('click', function() {
            if (!currentAgv) return;
            
            // Gửi dữ liệu draft lên server
            fetch('/api/send_request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agv_name: currentAgv,
                    state: draftState
                })
            })
            .then(res => res.json())
            .then(data => {
                console.log(data.message);
                
                // Sau khi gửi thành công, cập nhật trạng thái chính thức (agvStates)
                // Deep copy để tránh tham chiếu
                agvStates[currentAgv] = JSON.parse(JSON.stringify(draftState));

                // Hiệu ứng đổi màu nút trong 2s
                const originalText = btnSend.innerText;
                btnSend.classList.add('success-anim');
                btnSend.innerText = "Đã gửi!";
                setTimeout(() => {
                    btnSend.classList.remove('success-anim');
                    btnSend.innerText = originalText;
                }, 2000);
            })
            .catch(err => console.error("Lỗi gửi dữ liệu:", err));
        });
    }

    // 5. Sự kiện nút Đã hoàn thành (Giả lập tín hiệu)
    const btnComplete = document.getElementById('btn-complete');
    if (btnComplete) {
        btnComplete.addEventListener('click', function() {
            if (!currentAgv) return;

            fetch('/api/send_complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agv_name: currentAgv
                })
            })
            .then(res => res.json())
            .then(data => {
                console.log(data.message);
                
                // Hiệu ứng đổi màu nút trong 2s
                const originalText = btnComplete.innerText;
                btnComplete.classList.add('success-anim');
                btnComplete.innerText = "Đã xác nhận";
                setTimeout(() => {
                    btnComplete.classList.remove('success-anim');
                    btnComplete.innerText = originalText;
                }, 2000);
            })
            .catch(err => console.error("Lỗi gửi tín hiệu hoàn thành:", err));
        });
    }

    // 6. Khởi tạo OpenSeadragon (Bản đồ)
    if (document.getElementById('openseadragon-viewer')) {
        viewer = OpenSeadragon({
            id: "openseadragon-viewer",
            prefixUrl: "/static/openseadragon.min/images/", // Đường dẫn ảnh icon local
            tileSources: {
                type: 'image',
                url:  '/api/map_image' // Gọi API Flask
            },
            // Tùy chọn thêm để trải nghiệm tốt hơn
            animationTime: 0.5,
            blendTime: 0.1,
            maxZoomPixelRatio: 10, // Tăng giới hạn phóng to
            // Cho phép click vào overlay mà không bị trôi đi
            gestureSettingsMouse: {
                clickToZoom: false // Tắt click để zoom để tránh xung đột khi vẽ
            }
        });

        // --- Map Toolbar Logic ---
        
        // 1. Load Markers lúc khởi tạo
        loadMapMarkers();
        
        // Load Graph Data (Điểm và Đường từ t2.json)
        loadGraphData();

        // --- Sự kiện thay đổi toạ độ trực tiếp từ Input ---
        function updateMarkerPositionFromInput() {
            if (selectedMarkerIndex !== -1) {
                const xInput = parseInt(document.getElementById('marker-x').value);
                const yInput = parseInt(document.getElementById('marker-y').value);

                if (!isNaN(xInput) && !isNaN(yInput)) {
                    // Cập nhật dữ liệu (Lưu dạng Tỷ lệ = Pixel / Width)
                    mapMarkers[selectedMarkerIndex].x = xInput / mapImgWidth;
                    mapMarkers[selectedMarkerIndex].y = yInput / mapImgWidth;

                    // Cập nhật vị trí Overlay
                    const overlayElement = document.getElementById(`marker-${selectedMarkerIndex}`);
                    if (overlayElement) {
                        // OSD sử dụng Point(x, y)
                        viewer.updateOverlay(overlayElement, new OpenSeadragon.Point(xInput / mapImgWidth, yInput / mapImgWidth));
                    }
                }
            }
        }

        document.getElementById('marker-x').addEventListener('input', updateMarkerPositionFromInput);
        document.getElementById('marker-y').addEventListener('input', updateMarkerPositionFromInput);

        // 2. Sự kiện click lên bản đồ (Canvas)
        viewer.addHandler('canvas-click', function(event) {
            // Nếu toolbar đang ẩn thì không cho thao tác (thêm hoặc di chuyển)
            if (document.getElementById('map-toolbar').classList.contains('hidden')) return;

        // --- Logic chọn điểm chiếm dụng (Gần nhất) ---
        if (event.quick && isCreatingOccupiedRule && occSelectingType) {
            console.log("Đang chọn điểm chiếm dụng. Loại:", occSelectingType);
            var viewportPoint = viewer.viewport.pointFromPixel(event.position);
            var imagePoint = viewer.viewport.viewportToImageCoordinates(viewportPoint);
            
            let nearest = null;
            let minDist = 40; // Ngưỡng khoảng cách tối đa (pixel) để nhận diện điểm

            if (allGraphPoints.length === 0) {
                console.error("Lỗi: Danh sách allGraphPoints trống. Kiểm tra file t2.json hoặc API get_graph_data.");
            }

            allGraphPoints.forEach(p => {
                let d = Math.sqrt(Math.pow(imagePoint.x - p.x, 2) + Math.pow(imagePoint.y - p.y, 2));
                if (d < minDist) {
                    minDist = d;
                    nearest = p;
                }
            });

            if (nearest) {
                console.log("Đã tìm thấy điểm gần nhất:", nearest.name, "Khoảng cách:", minDist);
                if (occSelectingType === 'cond') {
                    if (currentOccCondition.length < 2 && !currentOccCondition.includes(nearest.name)) {
                        currentOccCondition.push(nearest.name);
                    }
                } else if (occSelectingType === 'lock') {
                    if (!tempLockStartPoint) {
                        // Lần click thứ nhất: Chọn điểm bắt đầu của đường khóa
                        tempLockStartPoint = nearest.name;
                    } else {
                        // Lần click thứ hai: Chọn điểm kết thúc để tạo thành một đường [P1, P2]
                        if (tempLockStartPoint !== nearest.name) {
                            currentOccLocked.push([tempLockStartPoint, nearest.name]);
                            tempLockStartPoint = null; // Reset để chọn cặp tiếp theo
                        }
                    }
                }
                updateOccupiedUI();
                return; // Ngăn không chạy tiếp logic của Marker (Kệ)
            } else {
                console.warn("Không tìm thấy điểm nào đủ gần vị trí click (minDist > 40px). Tọa độ click:", imagePoint.x, imagePoint.y);
            }
        }

            // Chỉ xử lý nếu không click vào overlay (quick check) và đang ở chế độ thêm
            if (event.quick && isAddingMarker) {
                // Chuyển đổi tọa độ pixel màn hình sang tọa độ điểm trên ảnh
                var viewportPoint = viewer.viewport.pointFromPixel(event.position);
                
                // Lấy tên từ input
                var nameInput = document.getElementById('marker-name-input');
                var groupInput = document.getElementById('marker-group-select'); // Mới
                var pointInput = document.getElementById('marker-point-input'); // Mới
                var widthInput = document.getElementById('marker-width');
                var heightInput = document.getElementById('marker-height');

                var name = nameInput.value.trim() || "Kệ " + (mapMarkers.length + 1);
                var w = widthInput.value ? parseInt(widthInput.value) : 50;
                var h = heightInput.value ? parseInt(heightInput.value) : 30;
                
                // Truyền thêm group và diem_lay_hang
                addMarkerToMap(viewportPoint, name, w, h, groupInput.value, pointInput.value);
                
                // Reset trạng thái
                isAddingMarker = false;
                document.getElementById('btn-add-marker').style.backgroundColor = ''; // Reset màu nút
                document.body.style.cursor = 'default';
            }
            // Logic di chuyển marker: Nếu đang chọn 1 marker và click vào chỗ trống
            else if (selectedMarkerIndex !== -1 && event.quick) {
                var viewportPoint = viewer.viewport.pointFromPixel(event.position);
                
                // Cập nhật tọa độ trong mảng dữ liệu
                mapMarkers[selectedMarkerIndex].x = viewportPoint.x;
                mapMarkers[selectedMarkerIndex].y = viewportPoint.y;

                // Cập nhật vị trí Overlay trên bản đồ
                var overlayElement = document.getElementById(`marker-${selectedMarkerIndex}`);
                if (overlayElement) {
                    viewer.updateOverlay(overlayElement, viewportPoint);
                }

                // Cập nhật giá trị vào ô input X, Y
                document.getElementById('marker-x').value = Math.round(viewportPoint.x * mapImgWidth);
                document.getElementById('marker-y').value = Math.round(viewportPoint.y * mapImgWidth);

                // Bỏ chọn sau khi di chuyển
                deselectMarker();
                document.getElementById('map-status').innerText = "Đã di chuyển kệ.";
                setTimeout(() => document.getElementById('map-status').innerText = "", 2000);
            }
        });

        // 3. Nút Thêm Kệ
        document.getElementById('btn-add-marker').addEventListener('click', function() {
            isAddingMarker = !isAddingMarker;
            if (isAddingMarker) {
                this.style.backgroundColor = '#f1c40f'; // Màu vàng báo hiệu đang active
                document.body.style.cursor = 'crosshair'; // Đổi con trỏ chuột
            } else {
                this.style.backgroundColor = '';
                document.body.style.cursor = 'default';
            }
        });

        // 4. Nút Lưu Bản Đồ
        document.getElementById('btn-save-map').addEventListener('click', function() {
            fetch('/api/save_markers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ markers: mapMarkers })
            })
            .then(res => res.json())
            .then(data => {
                alert(data.message);
            })
            .catch(err => console.error(err));
        });

        // 5. Nút Xóa Tất Cả
        document.getElementById('btn-clear-map').addEventListener('click', function() {
            if(confirm("Bạn có chắc chắn muốn xóa hết các đánh dấu?")) {
                viewer.clearOverlays();
                mapMarkers = [];
            }
        });
        
        // 8. Nút Cập Nhật Kệ Đang Chọn
        document.getElementById('btn-update-marker').addEventListener('click', function() {
            if (selectedMarkerIndex !== -1) {
                // Lấy giá trị từ input
                var nameInput = document.getElementById('marker-name-input');
                var groupInput = document.getElementById('marker-group-select');
                var pointInput = document.getElementById('marker-point-input');
                var widthInput = document.getElementById('marker-width');
                var heightInput = document.getElementById('marker-height');
                var xInput = document.getElementById('marker-x');
                var yInput = document.getElementById('marker-y');

                // Cập nhật dữ liệu mảng
                mapMarkers[selectedMarkerIndex].name = nameInput.value;
                mapMarkers[selectedMarkerIndex].group = groupInput.value;
                mapMarkers[selectedMarkerIndex].diem_lay_hang = pointInput.value;
                mapMarkers[selectedMarkerIndex].width = parseInt(widthInput.value) || 60;
                mapMarkers[selectedMarkerIndex].height = parseInt(heightInput.value) || 30;
                // Cập nhật toạ độ từ input (phòng trường hợp sửa số mà chưa click move)
                mapMarkers[selectedMarkerIndex].x = parseInt(xInput.value) / mapImgWidth;
                mapMarkers[selectedMarkerIndex].y = parseInt(yInput.value) / mapImgWidth;

                // Cập nhật hiển thị trên bản đồ (DOM Element)
                var elt = document.getElementById(`marker-${selectedMarkerIndex}`);
                if (elt) {
                    elt.innerText = mapMarkers[selectedMarkerIndex].name;
                    elt.style.width = mapMarkers[selectedMarkerIndex].width + "px";
                    elt.style.height = mapMarkers[selectedMarkerIndex].height + "px";
                    
                    // Cập nhật vị trí overlay theo số mới nhập
                    viewer.updateOverlay(elt, new OpenSeadragon.Point(mapMarkers[selectedMarkerIndex].x, mapMarkers[selectedMarkerIndex].y));
                }
                document.getElementById('map-status').innerText = "Đã cập nhật thông tin kệ.";
            }
        });

        // 7. Nút Xóa Kệ Đang Chọn
        document.getElementById('btn-delete-marker').addEventListener('click', function() {
            if (selectedMarkerIndex !== -1) {
                // Xóa overlay khỏi viewer
                viewer.removeOverlay(`marker-${selectedMarkerIndex}`);
                
                // Xóa khỏi mảng dữ liệu
                mapMarkers.splice(selectedMarkerIndex, 1);
                
                // Refresh lại toàn bộ marker để cập nhật lại ID (index) cho đúng thứ tự
                refreshAllMarkers();
                
                deselectMarker();
                document.getElementById('map-status').innerText = "Đã xóa kệ.";
            }
        });

        // 6. Ẩn/Hiện Toolbar
        document.getElementById('toggle-toolbar-btn').addEventListener('click', function() {
            const toolbar = document.getElementById('map-toolbar');
            toolbar.classList.toggle('hidden');
            
            // Nếu ẩn toolbar thì hủy chọn và hủy chế độ thêm để khóa chỉnh sửa
            if (toolbar.classList.contains('hidden')) {
                deselectMarker();
                isAddingMarker = false;
                document.getElementById('btn-add-marker').style.backgroundColor = '';
                document.body.style.cursor = 'default';
            }
        });

        // 9. Nút Ẩn/Hiện Điểm
        document.getElementById('btn-toggle-points').addEventListener('click', function() {
            this.classList.toggle('active');
            const isVisible = this.classList.contains('active');
            document.querySelectorAll('.graph-point').forEach(el => {
                el.classList.toggle('hidden-layer', !isVisible);
            });
        });

        // 10. Nút Ẩn/Hiện Đường
        document.getElementById('btn-toggle-paths').addEventListener('click', function() {
            this.classList.toggle('active');
            const isVisible = this.classList.contains('active');
            const svgLayer = document.getElementById('graph-svg-layer');
            if (svgLayer) {
                svgLayer.classList.toggle('hidden-layer', !isVisible);
            }
            
            // Ẩn/Hiện cả đường đi dự kiến của AGV
            if (dynamicPathSvg) {
                dynamicPathSvg.classList.toggle('hidden-layer', !isVisible);
            }
        });

        // --- Điểm Chiếm Dụng Logic ---
        const btnToggleOcc = document.getElementById('btn-toggle-occupied');
        const panelOcc = document.getElementById('occupied-points-panel');
        
        btnToggleOcc.addEventListener('click', function() {
            isCreatingOccupiedRule = !isCreatingOccupiedRule;
            this.classList.toggle('active');
            panelOcc.classList.toggle('hidden-layer');
            if (isCreatingOccupiedRule) loadOccupiedRules();
            else resetOccCreation();
        });

        document.getElementById('btn-occ-select-cond').addEventListener('click', () => {
            occSelectingType = 'cond';
            document.getElementById('btn-occ-select-cond').style.backgroundColor = '#f1c40f';
            document.getElementById('btn-occ-select-lock').style.backgroundColor = '';
        });

        document.getElementById('btn-occ-select-lock').addEventListener('click', () => {
            occSelectingType = 'lock';
            document.getElementById('btn-occ-select-lock').style.backgroundColor = '#f1c40f';
            document.getElementById('btn-occ-select-cond').style.backgroundColor = '';
        });

        document.getElementById('btn-occ-add-rule').addEventListener('click', function() {
            if (currentOccCondition.length === 0 || currentOccLocked.length === 0) {
                alert("Vui lòng chọn ít nhất 1 điểm xét và 1 điểm khóa.");
                return;
            }
            // Key là chuỗi các điểm xét cách nhau bởi dấu phẩy, giữ nguyên thứ tự để biết hướng đi
            const key = currentOccCondition.join(',');
            occupiedRules[key] = [...currentOccLocked];
            
            // Reset trạng thái chọn hiện tại nhưng vẫn giữ mode
            currentOccCondition = [];
            currentOccLocked = [];
            updateOccupiedUI();
        });

        document.getElementById('btn-save-occupied').addEventListener('click', function() {
            fetch('/api/save_occupied_points', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rules: occupiedRules })
            })
            .then(res => res.json())
            .then(data => alert(data.message))
            .catch(err => console.error(err));
        });

        window.removeOccRule = function(key) {
            if(confirm(`Xóa quy tắc cho ${key}?`)) {
                delete occupiedRules[key];
                updateOccupiedUI();
            }
        };

        // Hàm nạp quy tắc cũ để chỉnh sửa
        window.editOccRule = function(key) {
            currentOccCondition = key.split(',');
            // Nạp dữ liệu khóa (đảm bảo xử lý cả dữ liệu cũ dạng điểm và dữ liệu mới dạng đường)
            currentOccLocked = occupiedRules[key].map(item => Array.isArray(item) ? [...item] : item);
            updateOccupiedUI();
        };

        function loadOccupiedRules() {
            fetch('/api/get_occupied_points')
                .then(res => res.json())
                .then(data => {
                    occupiedRules = data || {};
                    updateOccupiedUI();
                });
        }

        function resetOccCreation() {
            occSelectingType = null;
            currentOccCondition = [];
            currentOccLocked = [];
            tempLockStartPoint = null;
            document.getElementById('btn-occ-select-cond').style.backgroundColor = '';
            document.getElementById('btn-occ-select-lock').style.backgroundColor = '';
        }

        // --- Hệ thống Cập nhật (Settings Tab) ---
        function refreshPendingFiles() {
            fetch('/api/get_uploaded_files')
                .then(res => res.json())
                .then(data => {
                    const list = document.getElementById('pending-files-list');
                    if (data.files && data.files.length > 0) {
                        list.innerHTML = data.files.map(f => `<li><i class="fa-solid fa-file"></i> ${f}</li>`).join('');
                    } else {
                        list.innerHTML = '<li>Chưa có file nào</li>';
                    }
                });
        }

        const btnRefresh = document.getElementById('btn-refresh-files');
        if (btnRefresh) {
            btnRefresh.addEventListener('click', refreshPendingFiles);
            // Gọi lần đầu khi load trang
            refreshPendingFiles();
        }

        const btnClearUpload = document.getElementById('btn-clear-upload');
        if (btnClearUpload) {
            btnClearUpload.addEventListener('click', function() {
                if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ file đang chờ trong thư mục upload?")) return;
                fetch('/api/clear_upload_folder', { method: 'POST' })
                    .then(res => res.json())
                    .then(data => {
                        document.getElementById('update-status-msg').innerText = data.message;
                        refreshPendingFiles();
                    })
                    .catch(err => {
                        console.error(err);
                        alert("Lỗi khi xóa file.");
                    });
            });
        }

        const btnUpload = document.getElementById('btn-upload-now');
        if (btnUpload) {
            btnUpload.addEventListener('click', function() {
                const fileInput = document.getElementById('update-file-input');
                if (fileInput.files.length === 0) {
                    alert("Vui lòng chọn file trước.");
                    return;
                }
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);

                fetch('/api/upload_update_file', {
                    method: 'POST',
                    body: formData
                })
                .then(res => res.json())
                .then(data => {
                    document.getElementById('update-status-msg').innerText = data.message;
                    refreshPendingFiles();
                    fileInput.value = '';
                })
                .catch(err => console.error(err));
            });
        }

        const btnApply = document.getElementById('btn-apply-system-update');
        if (btnApply) {
            btnApply.addEventListener('click', function() {
                if (!confirm("Hệ thống sẽ thay thế file hiện tại và tạo bản backup. Tiếp tục?")) return;
                
                btnApply.disabled = true;
                btnApply.innerText = "Đang xử lý...";
                
                fetch('/api/apply_update', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    document.getElementById('update-status-msg').innerText = data.message;
                    refreshPendingFiles();
                    btnApply.disabled = false;
                    btnApply.innerHTML = '<i class="fa-solid fa-file-import"></i> 1. CẬP NHẬT TẠI CHỖ (APPLY)';
                })
                .catch(err => console.error(err));
            });
        }

        const btnDeploy = document.getElementById('btn-deploy-all');
        if (btnDeploy) {
            btnDeploy.addEventListener('click', function() {
                if (!confirm("Ra lệnh cho tất cả AGV khác đồng bộ dữ liệu từ Server này?")) return;
                document.getElementById('update-status-msg').innerText = "Đang gửi lệnh tới các AGV...";
                
                fetch('/api/deploy_to_all_agvs', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    let details = Object.entries(data.details).map(([id, msg]) => `${id}: ${msg}`).join('\n');
                    document.getElementById('update-status-msg').innerText = "Kết quả Deploy:\n" + details;
                })
                .catch(err => {
                    document.getElementById('update-status-msg').innerText = "Lỗi Deploy: " + err;
                });
            });
        }

        // --- Quản lý kết nối AGV (Connection Status) ---
        function updateConnectionStatus() {
            fetch('/api/get_connected_agvs')
                .then(res => res.json())
                .then(data => {
                    const tbody = document.getElementById('connection-list-body');
                    if (!tbody) return;
                    
                    if (data.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="4" style="padding: 10px; text-align: center; color: #999;">Chưa có AGV nào kết nối</td></tr>';
                        return;
                    }

                    tbody.innerHTML = data.map(agv => {
                        const isOnline = agv.seconds_ago <= 10;
                        const statusText = isOnline ? 'Kết nối' : 'Mất kết nối';
                        const statusColor = isOnline ? '#27ae60' : '#e74c3c';
                        const timeText = agv.seconds_ago > 3600 ? "N/A" : `${agv.seconds_ago} giây trước`;

                        return `
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold; color: #2c3e50;">${agv.id.toUpperCase()}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee;">
                                    <a href="http://${agv.address}" target="_blank" style="color: #3498db; text-decoration: none;">
                                        <i class="fa-solid fa-external-link-square"></i> ${agv.address}
                                    </a>
                                </td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold; color: ${statusColor};">
                                    ${statusText}
                                </td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; color: ${statusColor};">
                                    ${timeText}
                                </td>
                            </tr>
                        `;
                    }).join('');
                });
        }

        // Cập nhật trạng thái kết nối mỗi 2 giây
        setInterval(updateConnectionStatus, 2000);
        updateConnectionStatus();
    }
});

// --- Backup Management Functions ---
async function loadBackupList() {
    const container = document.getElementById('backup-list-container');
    container.innerHTML = '<p class="text-muted">Đang tải danh sách sao lưu...</p>';

    try {
        const response = await fetch('/api/list_backups');
        const backups = await response.json();

        if (backups.length === 0) {
            container.innerHTML = '<p class="text-muted">Chưa có bản sao lưu nào.</p>';
            return;
        }

        container.innerHTML = ''; // Xóa thông báo "Đang tải..."
        backups.forEach(backup => {
            const backupItem = document.createElement('div');
            backupItem.className = 'backup-card-item';
            backupItem.innerHTML = `
                <h4><i class="fa-solid fa-box-archive"></i> Bản sao lưu: ${backup.timestamp}</h4>
                <button class="action-btn btn-primary" style="padding: 8px 12px; font-size: 0.9rem;" 
                        onclick="showBackupDetails('${backup.timestamp}', ${JSON.stringify(backup.files_backed_up).replace(/"/g, '&quot;')})">
                    <i class="fa-solid fa-eye"></i> Xem chi tiết file
                </button>
            `;
            container.appendChild(backupItem);
        });

    } catch (error) {
        console.error("Lỗi khi tải danh sách sao lưu:", error);
        container.innerHTML = '<p class="text-muted" style="color: red;">Lỗi khi tải danh sách sao lưu.</p>';
    }
}

function showBackupDetails(timestamp, files) {
    const modal = document.getElementById('backup-detail-modal');
    document.getElementById('modal-backup-timestamp').innerText = timestamp;
    const filesContainer = document.getElementById('modal-backup-files');
    filesContainer.innerHTML = '';

    if (files.length === 0) {
        filesContainer.innerHTML = '<p>Không có file nào trong bản sao lưu này.</p>';
    } else {
        files.forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.className = 'backup-file-item';
            fileItem.innerHTML = `
                <span><i class="fa-solid fa-file"></i> ${file.filename}</span>
                <button class="action-btn btn-primary" style="padding: 5px 10px; font-size: 0.8rem;" 
                        onclick="restoreFile('${timestamp}', '${file.filename}', '${file.original_target_rel_path}')">
                    <i class="fa-solid fa-rotate-left"></i> Khôi phục
                </button>
            `;
            filesContainer.appendChild(fileItem);
        });
    }
    modal.style.display = 'flex';
}

function closeBackupDetailModal() {
    document.getElementById('backup-detail-modal').style.display = 'none';
}

async function restoreFile(timestamp, filename, original_target_rel_path) {
    if (!confirm(`Bạn có chắc chắn muốn khôi phục file "${filename}" từ bản sao lưu "${timestamp}" không?`)) {
        return;
    }

    try {
        const response = await fetch('/api/restore_backup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timestamp, filename, original_target_rel_path })
        });
        const result = await response.json();
        alert(result.message);
        if (result.status === 'success' && filename === 'log_odds.npy') {
            window.location.reload(); // Tải lại trang để cập nhật bản đồ nếu file bản đồ được khôi phục
        }
    } catch (error) {
        console.error("Lỗi khi khôi phục file:", error);
        alert("Lỗi khi khôi phục file: " + error.message);
    }
}

// Hàm tính toán màu tương phản (Đen hoặc Trắng) dựa trên độ sáng của màu nền
function getContrastColor(rgb) {
    if (!rgb) return '#ffffff';
    // Công thức tính độ sáng YIQ
    const brightness = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000;
    return brightness > 125 ? '#000000' : '#ffffff';
}




function updateOccupiedUI() {
    // 1. Hiển thị danh sách điểm Đang Xét dưới dạng Tag (giữ nguyên thứ tự chọn)
    const condList = document.getElementById('occ-condition-list');
    condList.innerHTML = '';
    if (currentOccCondition.length === 0) condList.innerText = '-';
    else {
        currentOccCondition.forEach((p, idx) => {
            const tag = document.createElement('span');
            tag.className = 'occ-tag cond';
            tag.innerHTML = `${p} <i class="fa-solid fa-xmark"></i>`;
            tag.onclick = () => { currentOccCondition.splice(idx, 1); updateOccupiedUI(); };
            condList.appendChild(tag);
        });
    }

    // 2. Hiển thị danh sách đường Sẽ Khóa dưới dạng Tag (Dạng P1→P2)
    const lockList = document.getElementById('occ-locked-list');
    lockList.innerHTML = '';
    
    currentOccLocked.forEach((item, idx) => {
        const tag = document.createElement('span');
        tag.className = 'occ-tag lock';
        const displayText = Array.isArray(item) ? `${item[0]}→${item[1]}` : item;
        tag.innerHTML = `${displayText} <i class="fa-solid fa-xmark"></i>`;
        tag.onclick = () => { currentOccLocked.splice(idx, 1); updateOccupiedUI(); };
        lockList.appendChild(tag);
    });

    // Hiển thị trạng thái đang chọn dở dang cho đường khóa
    if (tempLockStartPoint) {
        const hint = document.createElement('span');
        hint.style.fontSize = '0.75rem';
        hint.style.color = '#e67e22';
        hint.style.marginLeft = '5px';
        hint.innerText = `(Chờ chọn đích cho: ${tempLockStartPoint} → ?)`;
        lockList.appendChild(hint);
    }

    if (currentOccLocked.length === 0 && !tempLockStartPoint) lockList.innerText = '-';

    // 3. Hiển thị danh sách quy tắc đã lưu với nút Sửa/Xóa
    const list = document.getElementById('occ-rules-list');
    list.innerHTML = '';
    Object.entries(occupiedRules).forEach(([key, val]) => {
        const item = document.createElement('div');
        item.className = 'occ-rule-item';
        item.innerHTML = `
            <div style="flex:1; cursor:pointer; font-size: 0.75rem;" onclick="editOccRule('${key}')">
                <b>${key.split(',').join(' & ')}:</b> [${val.map(v => Array.isArray(v) ? v.join('→') : v).join(', ')}]
            </div>
            <div style="display:flex; gap:10px;">
                <i class="fa-solid fa-pen-to-square" style="color:#3498db; cursor:pointer;" onclick="editOccRule('${key}')" title="Sửa"></i>
                <i class="fa-solid fa-trash" style="color:#e74c3c; cursor:pointer;" onclick="removeOccRule('${key}')" title="Xóa"></i>
            </div>
        `;
        list.appendChild(item);
    });
}

// --- Map Helper Functions ---

function deselectMarker() {
    // Bỏ class selected khỏi tất cả marker
    document.querySelectorAll('.shelf-marker').forEach(el => el.classList.remove('selected-marker'));
    selectedMarkerIndex = -1;
    
    // Disable nút xóa
    document.getElementById('btn-delete-marker').disabled = true;
    document.getElementById('btn-update-marker').disabled = true;
    // Reset inputs
    document.getElementById('marker-name-input').value = "";
    document.getElementById('marker-width').value = "";
    document.getElementById('marker-height').value = "";
    document.getElementById('marker-group-select').value = "";
    document.getElementById('marker-point-input').value = "";
    document.getElementById('marker-x').value = "";
    document.getElementById('marker-y').value = "";
    document.getElementById('map-status').innerText = "";
}

function refreshAllMarkers() {
    viewer.clearOverlays();
    const currentData = [...mapMarkers];
    mapMarkers = []; 
    
    currentData.forEach(m => {
        var point = new OpenSeadragon.Point(m.x, m.y);
        addMarkerToMap(point, m.name, m.width, m.height, m.group, m.diem_lay_hang);
    });
}

function loadMapMarkers() {
    fetch('/api/get_markers')
        .then(res => res.json())
        .then(data => {
            if (data.markers) {
                mapMarkers = []; // Reset trước khi load
                data.markers.forEach(m => {
                    var point = new OpenSeadragon.Point(m.x, m.y);
                    // Load đầy đủ thông tin: group, diem_lay_hang
                    addMarkerToMap(point, m.name, m.width, m.height, m.group, m.diem_lay_hang);
                });
            }
        })
        .catch(err => console.error("Lỗi tải marker:", err));
}

function addMarkerToMap(point, name, width, height, group, diem_lay_hang) {
    // Index của marker này trong mảng mapMarkers sắp được push
    const myIndex = mapMarkers.length;
    
    // Giá trị mặc định nếu không truyền vào
    width = width || 60;
    height = height || 30;
    group = group || "";
    diem_lay_hang = diem_lay_hang || "";
    
    // Tạo phần tử HTML cho marker
    var elt = document.createElement("div");
    elt.id = `marker-${myIndex}`; // Gán ID để dễ quản lý
    elt.className = "shelf-marker";
    
    // Set kích thước
    elt.style.width = width + "px";
    elt.style.height = height + "px";
    
    // Nội dung chỉ là tên
    elt.innerText = name;

    // Sự kiện click vào chính marker để chọn
    elt.addEventListener('click', function(e) {
        // Ngăn không cho sự kiện click lan xuống bản đồ (tránh kích hoạt thêm mới hoặc di chuyển nhầm)
        e.preventDefault();
        e.stopPropagation();

        // Nếu toolbar đang ẩn thì không cho thao tác chọn
        if (document.getElementById('map-toolbar').classList.contains('hidden')) return;

        // Nếu đang active chế độ thêm thì không cho chọn
        if (isAddingMarker) return;

        // Xử lý chọn
        deselectMarker(); // Bỏ chọn cái cũ
        
        selectedMarkerIndex = myIndex;
        this.classList.add('selected-marker');
        
        // Enable nút xóa
        document.getElementById('btn-delete-marker').disabled = false;
        document.getElementById('btn-update-marker').disabled = false;

        // Đổ dữ liệu của marker đang chọn vào các ô input để sửa
        document.getElementById('marker-name-input').value = mapMarkers[myIndex].name;
        document.getElementById('marker-width').value = mapMarkers[myIndex].width;
        document.getElementById('marker-height').value = mapMarkers[myIndex].height;
        document.getElementById('marker-group-select').value = mapMarkers[myIndex].group || "";
        document.getElementById('marker-point-input').value = mapMarkers[myIndex].diem_lay_hang || "";
        document.getElementById('marker-x').value = Math.round(mapMarkers[myIndex].x * mapImgWidth);
        document.getElementById('marker-y').value = Math.round(mapMarkers[myIndex].y * mapImgWidth);

        // Hiển thị thêm thông tin điểm lấy hàng nếu có
        const infoPoint = mapMarkers[myIndex].diem_lay_hang ? ` (Điểm lấy: ${mapMarkers[myIndex].diem_lay_hang})` : '';
        document.getElementById('map-status').innerText = `Đang chọn: ${name}${infoPoint}. Click nền để di chuyển.`;
    });
    
    // Thêm MouseTracker để OpenSeadragon cho phép tương tác click lên element này
    new OpenSeadragon.MouseTracker({
        element: elt,
        clickHandler: function(e) {
            // Cần thiết để OSD nhận diện click trên overlay
            // Logic click đã xử lý ở addEventListener native bên trên
        }
    });

    // Thêm Overlay vào OpenSeadragon
    viewer.addOverlay({
        element: elt,
        location: point,
        placement: 'CENTER' // Đưa tâm của kệ vào đúng tọa độ click/dữ liệu
    });

    // Luôn push vào mảng quản lý
    mapMarkers.push({ 
        x: point.x, 
        y: point.y, 
        name: name, 
        width: width, 
        height: height, 
        group: group,
        diem_lay_hang: diem_lay_hang 
    });
}

// Hàm tải trạng thái của 1 AGV lên giao diện
function loadAgvState(agvName) {
    // Lấy trạng thái đã lưu (Official) copy sang trạng thái nháp (Draft)
    // Nếu chưa lưu lần nào, lấy từ agvStates khởi tạo ban đầu
    draftState = JSON.parse(JSON.stringify(agvStates[agvName]));

    const state = draftState;

    // Duyệt qua các input và set giá trị
    for (const [key, value] of Object.entries(state)) {
        const input = document.querySelector(`.dynamic-options [name="${key}"]`);
        if (input) {
            if (input.type === 'checkbox') {
                input.checked = (value === 'on');
            } else {
                input.value = value;
            }

            // Xử lý đặc biệt cho combobox giá hàng để hiển thị đúng nút bên phải
            if (key === 'chon_gia_hang') {
                renderShelfButtons(value);
            }
        }
    }

    // Tải danh sách các giá kệ đã chọn lên UI
    renderSelectedList();
}

function loadGraphData() {
    fetch('/api/get_graph_data')
        .then(res => res.json())
        .then(data => {
            if (!data.points || !data.paths) return;
            
            mapImgWidth = data.dims[0]; // Lưu chiều rộng ảnh để tính toán tọa độ
            allGraphPaths = data.paths; // Lưu global để dùng cho vẽ đường đi động của AGV

            const pointsDatalist = document.getElementById('point-suggestions');

            // 1. Vẽ đường (Paths) bằng SVG Overlay
            // Tạo phần tử SVG bao trùm toàn bộ ảnh map
            const svgNS = "http://www.w3.org/2000/svg";
            const svgNode = document.createElementNS(svgNS, "svg");
            svgNode.id = 'graph-svg-layer';
            svgNode.setAttribute('class', 'graph-svg-overlay');
            // Đảm bảo SVG lấp đầy container và không giữ tỷ lệ mặc định gây lệch
            svgNode.setAttribute('width', '100%');
            svgNode.setAttribute('height', '100%');
            svgNode.setAttribute('preserveAspectRatio', 'none');
            
            // Nếu cấu hình ẩn đường thì thêm class hidden ngay từ đầu
            if (!CONFIG_SHOW_PATHS) svgNode.classList.add('hidden-layer');

            // Thiết lập viewBox tương ứng với kích thước ảnh gốc
            svgNode.setAttribute('viewBox', `0 0 ${data.dims[0]} ${data.dims[1]}`);
            
            // Vẽ từng đoạn đường
            data.paths.forEach(path => {
                if (path.type === 'curve' && path.control) {
                    // Vẽ đường cong Quadratic Bezier (Q)
                    const curve = document.createElementNS(svgNS, "path");
                    const d = `M ${path.start.x} ${path.start.y} Q ${path.control.x} ${path.control.y} ${path.end.x} ${path.end.y}`;
                    curve.setAttribute('d', d);
                    curve.setAttribute('fill', 'none');
                    curve.setAttribute('stroke', '#3498db');
                    curve.setAttribute('stroke-width', '2.5');
                    curve.setAttribute('stroke-linecap', 'round');
                    svgNode.appendChild(curve);
                } else {
                    const line = document.createElementNS(svgNS, "line");
                    line.setAttribute('x1', path.start.x);
                    line.setAttribute('y1', path.start.y);
                    line.setAttribute('x2', path.end.x);
                    line.setAttribute('y2', path.end.y);
                    line.setAttribute('stroke', '#3498db');
                    line.setAttribute('stroke-width', '2.5'); 
                    line.setAttribute('stroke-linecap', 'round');
                    svgNode.appendChild(line);
                }
            });

            // Tính toán tỷ lệ ảnh (Aspect Ratio) để đặt SVG đúng vị trí
            // Trong OpenSeadragon, chiều rộng ảnh = 1.0, chiều cao = Height / Width
            const aspectRatio = data.dims[1] / data.dims[0];

            // Thêm SVG vào Viewer như một Overlay phủ toàn bộ
            viewer.addOverlay({
                element: svgNode,
                // Rect(x, y, width, height) theo hệ tọa độ Viewport (0-1)
                location: new OpenSeadragon.Rect(0, 0, 1, aspectRatio), 
                checkResize: false // Không cần tính toán lại vì SVG tự scale
            });

            // --- 3. Tạo Layer cho đường đi động của AGV ---
            const dynamicSvg = document.createElementNS(svgNS, "svg");
            dynamicSvg.id = 'agv-dynamic-paths-layer';
            dynamicSvg.setAttribute('class', 'agv-path-svg-overlay');
            dynamicSvg.setAttribute('viewBox', `0 0 ${data.dims[0]} ${data.dims[1]}`);
            if (!CONFIG_SHOW_PATHS) dynamicSvg.classList.add('hidden-layer');

            viewer.addOverlay({
                element: dynamicSvg,
                location: new OpenSeadragon.Rect(0, 0, 1, aspectRatio),
                checkResize: false
            });
            dynamicPathSvg = dynamicSvg;

            // 2. Vẽ điểm (Points) bằng HTML Overlay
            data.points.forEach(p => {
                const pointDiv = document.createElement('div');
                pointDiv.className = 'graph-point';
                
                // Nếu cấu hình ẩn điểm thì thêm class hidden
                if (!CONFIG_SHOW_POINTS) pointDiv.classList.add('hidden-layer');
                
                pointDiv.title = p.name; // Tooltip tên điểm

                // Tạo nhãn tên điểm hiển thị bên cạnh
                const label = document.createElement('div');
                label.className = 'point-label';
                label.innerText = p.name;
                pointDiv.appendChild(label);
                
                // Chuyển đổi tọa độ Pixel -> Viewport
                // x_viewport = x_pixel / image_width
                // y_viewport = y_pixel / image_width (Chia cho width để giữ tỷ lệ 1:1)
                const vx = p.x / data.dims[0];
                const vy = p.y / data.dims[0];

                // Thêm điểm vào Viewer
                viewer.addOverlay({
                    element: pointDiv,
                    location: new OpenSeadragon.Point(vx, vy),
                    placement: 'TOP_LEFT', // Để CSS transform: translate(-50%, -50%) làm nhiệm vụ căn tâm
                    checkResize: false
                });

                // --- THÊM VÀO DATALIST GỢI Ý ---
                if (pointsDatalist) {
                    const option = document.createElement('option');
                    option.value = p.name;
                    // option.innerText = `(${p.x}, ${p.y})`; // Tuỳ chọn hiển thị thêm toạ độ
                    pointsDatalist.appendChild(option);
                }
            });

            allGraphPoints = data.points; // Lưu lại để dùng cho logic click gần nhất
        })
        .catch(err => console.error("Lỗi tải graph data:", err));
}

// Hàm hiển thị các nút giá hàng (A01, A02...) dựa trên lựa chọn (A, B...)
function renderShelfButtons(groupKey) {
    const container = document.getElementById('shelf-container');
    container.innerHTML = ''; // Xóa nội dung cũ

    const items = SHELF_DATA[groupKey];

    if (items && items.length > 0) {
        items.forEach(itemName => {
            const btn = document.createElement('button');
            btn.className = 'shelf-btn';
            btn.innerText = itemName;
            
            // Sự kiện click
            btn.onclick = function() {
                // Đổi màu trong 1s
                btn.classList.add('clicked');
                setTimeout(() => {
                    btn.classList.remove('clicked');
                }, 1000);

                // --- Logic thêm vào danh sách đã chọn ---
                // Thao tác trên Draft State
                if (currentAgv) {
                    if (!draftState['danh_sach_ke_da_chon']) {
                        draftState['danh_sach_ke_da_chon'] = [];
                    }
                    // Thêm vào mảng
                    draftState['danh_sach_ke_da_chon'].push(itemName);
                    console.log(`Added ${itemName} to ${currentAgv}`);
                    
                    // Cập nhật giao diện danh sách
                    renderSelectedList();
                }
            };

            container.appendChild(btn);
        });
    } else {
        container.innerHTML = '<p class="text-muted" style="grid-column: 1/-1;">Không có dữ liệu cho lựa chọn này.</p>';
    }
}

// Hàm render danh sách các item đã chọn (Tags)
function renderSelectedList() {
    const listContainer = document.getElementById('selected-list');
    if (!listContainer || !currentAgv) return;

    // Render từ Draft State
    const list = draftState['danh_sach_ke_da_chon'] || [];
    listContainer.innerHTML = '';

    if (list.length === 0) {
        listContainer.innerHTML = '<span style="color: #ccc; font-style: italic;">Chưa chọn giá nào</span>';
        return;
    }

    list.forEach((item, index) => {
        const tag = document.createElement('span');
        tag.className = 'tag-item';
        tag.innerText = item;
        
        // Sự kiện click vào tag để xóa
        tag.onclick = function() {
            // Xóa phần tử tại vị trí index
            draftState['danh_sach_ke_da_chon'].splice(index, 1);
            // Render lại
            renderSelectedList();
        };

        listContainer.appendChild(tag);
    });
}


// Hàm vẽ và cập nhật vị trí/góc quay của các AGV trên bản đồ
function updateAgvDisplay(states) {
    if (!viewer || mapImgWidth <= 1) return;

    // Xóa các đường đi cũ trước khi vẽ mới cho chu kỳ này
    if (dynamicPathSvg) {
        while (dynamicPathSvg.firstChild) {
            dynamicPathSvg.removeChild(dynamicPathSvg.firstChild);
        }
    }

    Object.entries(states).forEach(([id, state]) => {
        const coords = state.toa_do;
        const angle = state.goc_agv || 0;
        const rgb = AGV_COLORS[id] || [52, 152, 219];
        const color = `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
        const contrastColor = getContrastColor(rgb);
        const agvNumber = id.replace(/\D/g, ''); // Lấy phần số từ ID (ví dụ: agv1 -> 1)

        // Chuyển đổi tọa độ sang hệ Viewport của OSD
        const px_x = coords.x;
        const px_y = coords.y;
        const vx = px_x / mapImgWidth;
        const vy = px_y / mapImgWidth;

        // Tỷ lệ kích thước AGV so với bản đồ
        const vWidth = AGV_SIZE_PX[0] / mapImgWidth;
        const vHeight = AGV_SIZE_PX[1] / mapImgWidth;

        let agvObj = agvOverlays[id];

        if (!agvObj) {
            // 1. Tạo container cho AGV
            const container = document.createElement('div');
            container.className = 'agv-container';
            
            // Đặt aspectRatio ngay tại container để OSD tính toán được chiều cao chính xác khi căn giữa
            container.style.aspectRatio = `${AGV_SIZE_PX[0]} / ${AGV_SIZE_PX[1]}`;

            // 2. Tạo thân xe thực tế để xoay
            const body = document.createElement('div');
            body.className = 'agv-body';

            // 2. Vẽ toàn bộ AGV bằng SVG để tỷ lệ luôn chuẩn khi zoom
            body.innerHTML = `
                <svg viewBox="0 0 ${AGV_SIZE_PX[0]} ${AGV_SIZE_PX[1]}" class="agv-arrow-svg">
                    <!-- Thân xe -->
                    <rect x="0" y="0" width="${AGV_SIZE_PX[0]}" height="${AGV_SIZE_PX[1]}" 
                          fill="${color.replace('rgb', 'rgba').replace(')', ', 0.8)')}" 
                          stroke="#333" stroke-width="2" rx="4" ry="4" />
                    
                    <!-- Mũi tên hướng -->
                    <defs>
                        <marker id="arrowhead-${id}" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                            <polygon points="0 0, 8 3, 0 6" fill="${contrastColor}" />
                        </marker>
                    </defs>
                    <line x1="${AGV_SIZE_PX[0] / 2}" y1="${AGV_SIZE_PX[1] / 2}" 
                          x2="${AGV_SIZE_PX[0] * 0.85}" y2="${AGV_SIZE_PX[1] / 2}" 
                          stroke="${contrastColor}" stroke-width="2.5" marker-end="url(#arrowhead-${id})" stroke-linecap="round" />
                    
                    <!-- Số AGV (Nằm ở phía sau xe) -->
                    <text x="${AGV_SIZE_PX[0] * 0.25}" y="${AGV_SIZE_PX[1] / 2}" dominant-baseline="central" text-anchor="middle" 
                          fill="${contrastColor}" font-size="14" font-weight="bold" font-family="Arial">
                        ${agvNumber}
                    </text>
                </svg>
            `;

            container.appendChild(body);

            // Thêm lớp phủ xe (Có width để tự co giãn theo zoom)
            viewer.addOverlay({
                element: container,
                location: new OpenSeadragon.Point(vx, vy),
                placement: 'CENTER',
                width: vWidth
            });
            
            agvObj = { container: container, body: body };
            agvOverlays[id] = agvObj;
        } else {
            // Cập nhật vị trí
            viewer.updateOverlay(agvObj.container, new OpenSeadragon.Point(vx, vy));
        }

        // --- Vẽ đường đi dự kiến (Paths) ---
        if (dynamicPathSvg && state.danh_sach_duong_di && state.danh_sach_duong_di.length >= 2) {
            const pathElem = document.createElementNS("http://www.w3.org/2000/svg", "path");
            let d = "";
            let segmentsDrawn = 0;

            for (let i = 0; i < state.danh_sach_duong_di.length - 1; i++) {
                const sName = state.danh_sach_duong_di[i];
                const eName = state.danh_sach_duong_di[i+1];
                
                const sPt = allGraphPoints.find(p => p.name === sName);
                const ePt = allGraphPoints.find(p => p.name === eName);
                if (!sPt || !ePt) continue;

                if (segmentsDrawn === 0) d += `M ${sPt.x} ${sPt.y} `;
                segmentsDrawn++;

                // Tìm cạnh trong sơ đồ để kiểm tra loại đường
                const edge = allGraphPaths.find(p => 
                    (p.start_node === sName && p.end_node === eName) ||
                    (p.start_node === eName && p.end_node === sName)
                );

                if (edge && edge.type === 'curve' && edge.control) {
                    d += `Q ${edge.control.x} ${edge.control.y} ${ePt.x} ${ePt.y} `;
                } else {
                    d += `L ${ePt.x} ${ePt.y} `;
                }
            }
            
            if (segmentsDrawn > 0) {
                pathElem.setAttribute('d', d);
                pathElem.setAttribute('fill', 'none');
                pathElem.setAttribute('stroke', color);
                pathElem.setAttribute('stroke-width', '5');
                pathElem.setAttribute('stroke-opacity', '0.4');
                pathElem.setAttribute('stroke-linecap', 'round');
                pathElem.setAttribute('stroke-linejoin', 'round');
                dynamicPathSvg.appendChild(pathElem);
            }
        } else if (dynamicPathSvg && state.danh_sach_toa_do_duong_di && state.danh_sach_toa_do_duong_di.length >= 2) {
            // Fallback nếu không có danh sách tên điểm
            const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
            const pointsAttr = state.danh_sach_toa_do_duong_di.map(p => `${p[0]},${p[1]}`).join(' ');
            polyline.setAttribute('points', pointsAttr);
            polyline.setAttribute('fill', 'none');
            polyline.setAttribute('stroke', color);
            polyline.setAttribute('stroke-width', '5');
            polyline.setAttribute('stroke-opacity', '0.4');
            polyline.setAttribute('stroke-linecap', 'round');
            polyline.setAttribute('stroke-linejoin', 'round');
            dynamicPathSvg.appendChild(polyline);
        }

        // Cập nhật góc quay (Rotation)
        agvObj.body.style.transform = `rotate(${-angle}deg)`;
    });
}