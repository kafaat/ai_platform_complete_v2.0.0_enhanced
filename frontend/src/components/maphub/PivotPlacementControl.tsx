interface Props {
  getCenter: () => { lat: number; lng: number } | undefined;
  onPlace: (lat: number, lng: number) => void;
}

export function PivotPlacementControl({ getCenter, onPlace }: Props) {
  return (
    <div
      dir="rtl" data-testid="pivot-designer-map-hint"
      className="absolute start-3 top-12 z-[1000] max-w-[85%] rounded-lg bg-slate-900 px-3 py-2 text-xs text-white"
    >
      <p>انقر لاختيار مركز المحوري، أو حرّك الخريطة بالأسهم ثم اختر</p>
      <button
        type="button" className="mt-1 rounded px-2 py-1 font-semibold underline"
        onClick={() => {
          const center = getCenter();
          if (center) onPlace(center.lat, center.lng);
        }}
      >
        وضع المحوري في مركز الخريطة
      </button>
    </div>
  );
}
