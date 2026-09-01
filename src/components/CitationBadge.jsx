export default function CitationBadge({ number, sourceId, isActive, onSelect }) {
  return (
    <button
      onClick={() => onSelect(sourceId)}
      className={`mx-0.5 inline-flex h-4 min-w-[16px] -translate-y-0.5 items-center justify-center rounded-full px-1 align-middle text-[10px] font-semibold leading-none transition-colors ${
        isActive
          ? "bg-signal-600 text-white"
          : "bg-signal-500/15 text-signal-600 hover:bg-signal-500/25"
      }`}
      aria-label={`View source ${number}`}
    >
      {number}
    </button>
  );
}
