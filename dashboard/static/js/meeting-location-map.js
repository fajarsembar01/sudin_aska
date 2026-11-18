/* Meeting location picker, using the same Leaflet/OSM map as Panbers. */
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.meeting-location-map').forEach(function (container) {
    const form = container.closest('form');
    const modal = container.closest('.modal');
    const latitude = form.querySelector('[name="latitude"]');
    const longitude = form.querySelector('[name="longitude"]');
    const radius = form.querySelector('[name="radius_m"]');
    const message = form.querySelector('.location-setup-status');
    let map;
    let marker;
    let circle;

    function pointFromFields() {
      if (!latitude.value.trim() || !longitude.value.trim()) return null;
      const lat = Number(latitude.value);
      const lng = Number(longitude.value);
      return Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180
        ? [lat, lng] : null;
    }

    function updateMap(fit) {
      if (!map) return;
      const point = pointFromFields();
      if (!point) {
        if (marker) map.removeLayer(marker);
        if (circle) map.removeLayer(circle);
        marker = circle = null;
        map.setView([-6.2088, 106.8456], 11);
        return;
      }
      if (!marker) {
        marker = L.marker(point, {draggable: true, title: 'Titik lokasi meeting'}).addTo(map);
        marker.on('dragend', function () { selectPoint(marker.getLatLng()); });
      } else {
        marker.setLatLng(point);
      }
      const meters = Math.max(1, Math.min(100000, Number(radius.value) || 200));
      if (!circle) {
        circle = L.circle(point, {radius: meters, color: '#0d6efd', fillOpacity: 0.12}).addTo(map);
      } else {
        circle.setLatLng(point).setRadius(meters);
      }
      if (fit) map.fitBounds(circle.getBounds(), {padding: [24, 24], maxZoom: 17});
    }

    function selectPoint(point) {
      latitude.value = point.lat.toFixed(7);
      longitude.value = point.lng.toFixed(7);
      form.querySelector('.location-favorite').value = '';
      message.textContent = 'Titik meeting dipilih dari peta. Geser pin untuk menyesuaikan lokasi.';
      updateMap(false);
    }

    modal.addEventListener('shown.bs.modal', function () {
      if (!window.L) {
        message.textContent = 'Peta gagal dimuat. Periksa koneksi lalu buka kembali form meeting. Lokasi perangkat dan favorit tetap dapat digunakan.';
        return;
      }
      if (!map) {
        map = L.map(container).setView([-6.2088, 106.8456], 11);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '&copy; OpenStreetMap contributors',
          maxZoom: 19
        }).addTo(map);
        map.on('click', function (event) { selectPoint(event.latlng); });
      }
      map.invalidateSize();
      updateMap(true);
    });
    form.addEventListener('submit', function (event) {
      if (!pointFromFields()) {
        event.preventDefault();
        message.textContent = 'Pilih titik lokasi meeting di peta terlebih dahulu.';
        container.focus();
      }
    });
    radius.addEventListener('input', function () { updateMap(true); });
    form.addEventListener('meeting-location-change', function () { updateMap(true); });
  });
});
