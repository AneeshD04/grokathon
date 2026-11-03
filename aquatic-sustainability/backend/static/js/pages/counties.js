(function countiesData() {
  function bboxPath(bbox) {
    const [minLon, minLat, maxLon, maxLat] = bbox;
    return [
      { lat: minLat, lng: minLon },
      { lat: minLat, lng: maxLon },
      { lat: maxLat, lng: maxLon },
      { lat: maxLat, lng: minLon },
    ];
  }

  function county(id, name, bbox) {
    return { id: id, name: name, bbox: bbox, path: bboxPath(bbox) };
  }

  // Census-style county envelopes as [minLon, minLat, maxLon, maxLat]
  // so GET /api/cameras and POST /api/watches can use the same geofence.
  const COUNTIES = [
    county("galveston-county", "Galveston County", [-95.1544, 29.0668, -94.3684, 29.5931]),
    county("harris-county", "Harris County", [-95.9607, 29.4972, -94.9082, 30.1704]),
  ];

  window.OEM_COUNTIES = COUNTIES;
  window.oemCountyById = function oemCountyById(id) {
    return COUNTIES.find(function (row) {
      return row.id === id;
    });
  };
})();
