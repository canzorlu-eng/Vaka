import React from "react";

// FDI numbering. Upper: 18-11 | 21-28. Lower: 48-41 | 31-38.
const UPPER = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28];
const LOWER = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38];

const Tooth = ({ n, selected, highlighted, onClick }) => {
  let fill = "#FFFFFF";
  let stroke = "#E3DED6";
  if (highlighted) { fill = "#FFE0D6"; stroke = "#FF937B"; }
  if (selected) { fill = "#FF937B"; stroke = "#E0705A"; }
  return (
    <button
      data-testid={`tooth-${n}`}
      onClick={() => onClick(n)}
      className="flex flex-col items-center gap-0.5 group"
      title={`${n}`}
    >
      <svg width="22" height="26" viewBox="0 0 22 26" className="transition-transform group-hover:scale-110">
        <path
          d="M4 6 C4 1 18 1 18 6 C20 12 17 16 15 24 C14 26 13 25 12.5 22 C12 20 10 20 9.5 22 C9 25 8 26 7 24 C5 16 2 12 4 6 Z"
          fill={fill}
          stroke={stroke}
          strokeWidth="1.5"
        />
      </svg>
      <span className={`text-[9px] font-semibold ${selected ? "text-primary" : "text-muted-foreground"}`}>{n}</span>
    </button>
  );
};

export const Odontogram = ({ selected, highlighted = [], onSelect }) => {
  return (
    <div data-testid="odontogram" className="card-medkit p-4 select-none">
      <div className="flex justify-center gap-0.5 mb-3 flex-wrap">
        {UPPER.map((n) => (
          <Tooth key={n} n={n} selected={selected === n} highlighted={highlighted.includes(n)} onClick={onSelect} />
        ))}
      </div>
      <div className="border-t-2 border-dashed border-border my-1" />
      <div className="flex justify-center gap-0.5 mt-3 flex-wrap">
        {LOWER.map((n) => (
          <Tooth key={n} n={n} selected={selected === n} highlighted={highlighted.includes(n)} onClick={onSelect} />
        ))}
      </div>
    </div>
  );
};
