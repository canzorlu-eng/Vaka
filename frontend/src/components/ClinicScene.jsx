import React from "react";

// Cozy isometric dental clinic scene with a patient in the chair.
// mood: 'neutral' | 'pain' | 'anxious'
export const ClinicScene = ({ mood = "neutral", speaking = false }) => {
  const cheek = mood === "pain" ? "#F4A9A0" : "#F6C9B0";
  const browY = mood === "pain" ? 4 : mood === "anxious" ? -2 : 0;

  return (
    <div data-testid={`clinic-scene-${mood}`} className="relative w-full h-full flex items-end justify-center overflow-hidden">
      {/* room backdrop */}
      <svg viewBox="0 0 480 360" className="absolute inset-0 w-full h-full" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#FBEFE4" />
            <stop offset="1" stopColor="#F5E4D3" />
          </linearGradient>
          <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#EAD9C4" />
            <stop offset="1" stopColor="#E0CBB0" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="480" height="250" fill="url(#wall)" />
        <polygon points="0,250 480,250 480,360 0,360" fill="url(#floor)" />
        {/* window */}
        <rect x="40" y="45" width="120" height="95" rx="14" fill="#CDE8DD" stroke="#B4D8C8" strokeWidth="4" />
        <line x1="100" y1="45" x2="100" y2="140" stroke="#B4D8C8" strokeWidth="4" />
        <line x1="40" y1="92" x2="160" y2="92" stroke="#B4D8C8" strokeWidth="4" />
        {/* plant */}
        <rect x="360" y="150" width="46" height="46" rx="8" fill="#E8A98E" />
        <path d="M383 150 C 370 120 360 118 366 100 C 380 112 384 128 383 150" fill="#82C3A6" />
        <path d="M383 150 C 396 122 408 122 404 102 C 388 112 384 130 383 150" fill="#6FB595" />
        {/* wall cross emblem */}
        <circle cx="245" cy="70" r="26" fill="#FFE2D8" />
        <path d="M245 56v28M231 70h28" stroke="#FF937B" strokeWidth="6" strokeLinecap="round" />
        {/* shelf */}
        <rect x="200" y="120" width="90" height="10" rx="4" fill="#D9BFA3" />
        <rect x="210" y="104" width="14" height="16" rx="3" fill="#82C3A6" />
        <rect x="230" y="100" width="14" height="20" rx="3" fill="#FF937B" />
        <rect x="250" y="106" width="14" height="14" rx="3" fill="#F0C86A" />
      </svg>

      {/* dental chair + patient */}
      <svg viewBox="0 0 300 300" className="relative w-[62%] max-w-[280px] animate-breath" style={{ zIndex: 2 }}>
        {/* chair base */}
        <rect x="70" y="250" width="160" height="24" rx="12" fill="#B9A488" />
        <rect x="118" y="220" width="64" height="42" rx="10" fill="#A48C6E" />
        {/* chair back */}
        <rect x="60" y="70" width="180" height="180" rx="34" fill="#7FB39A" />
        <rect x="74" y="84" width="152" height="150" rx="26" fill="#96C9B4" />

        {/* body */}
        <rect x="108" y="150" width="84" height="90" rx="30" fill="#7EA9D8" />
        {/* neck */}
        <rect x="132" y="130" width="36" height="30" rx="12" fill="#F6C9B0" />
        {/* head */}
        <circle cx="150" cy="108" r="42" fill="#F6C9B0" />
        {/* hair */}
        <path d="M108 100 C 108 66 192 66 192 100 C 192 86 178 74 150 74 C 122 74 108 86 108 100Z" fill="#5C4A3D" />
        {/* cheeks */}
        <circle cx="123" cy="118" r="9" fill={cheek} opacity="0.7" />
        <circle cx="177" cy="118" r="9" fill={cheek} opacity="0.7" />
        {/* eyes */}
        {mood === "pain" ? (
          <>
            <path d="M128 104 l16 6" stroke="#3B3330" strokeWidth="4" strokeLinecap="round" />
            <path d="M172 104 l-16 6" stroke="#3B3330" strokeWidth="4" strokeLinecap="round" />
          </>
        ) : (
          <>
            <circle cx="134" cy="106" r="4.5" fill="#3B3330" />
            <circle cx="166" cy="106" r="4.5" fill="#3B3330" />
          </>
        )}
        {/* brows */}
        <path d={`M126 ${94 + browY} q8 -6 18 -2`} stroke="#5C4A3D" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        <path d={`M174 ${94 + browY} q-8 -6 -18 -2`} stroke="#5C4A3D" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        {/* mouth */}
        {mood === "pain" ? (
          <ellipse cx="150" cy="130" rx="9" ry="7" fill="#B5544A" />
        ) : mood === "anxious" ? (
          <path d="M138 132 q12 -8 24 0" stroke="#B5544A" strokeWidth="3.5" fill="none" strokeLinecap="round" />
        ) : (
          <path d="M138 128 q12 9 24 0" stroke="#B5544A" strokeWidth="3.5" fill="none" strokeLinecap="round" />
        )}
        {/* anxious sweat drop */}
        {mood === "anxious" && <path d="M196 100 q6 10 0 16 q-6 -6 0 -16" fill="#9CC8E6" />}
        {/* speaking indicator glow near mouth */}
        {speaking && <circle cx="150" cy="130" r="14" fill="none" stroke="#FF937B" strokeWidth="2.5" opacity="0.5" className="animate-pulse" />}
      </svg>
    </div>
  );
};
