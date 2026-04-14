document.addEventListener('DOMContentLoaded', function () {
  OpenSeadragon({
    id: "openseadragon-viewer",
    prefixUrl: "/static/images/",
    tileSources: {
      type: 'image',
      url: '/full_image.jpg?' + new Date().getTime(),
    },
    showNavigator: true,
    navigatorPosition: "TOP_RIGHT",
  });
});

function updateSetting(key, value) {
  fetch('/update_setting', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: key, value: parseInt(value) })
  })
  .then(res => res.json())
  .then(data => console.log("Update:", data))
  .catch(err => console.error(err));
}

function confirmAGVUpdate() {
  const x = document.getElementById('inputAgvX').value;
  const y = document.getElementById('inputAgvY').value;
  const angle = document.getElementById('inputAgvAngle').value;
  alert(`AGV cập nhật: X=${x}, Y=${y}, Góc=${angle}`);
}
