interface NumberStepperProps {
  value: string;
  onChange: (value: string) => void;
  min: number;
  max: number;
  step: number;
  decimals?: number;
}

export default function NumberStepper({ value, onChange, min, max, step, decimals = 2 }: NumberStepperProps) {
  const adjust = (direction: -1 | 1) => {
    const current = Number(value);
    const base = Number.isFinite(current) ? current : min;
    const next = Math.min(max, Math.max(min, base + direction * step));
    onChange(next.toFixed(decimals));
  };

  return (
    <div className="flex items-center gap-2">
      <button type="button" className="btn-ghost !px-3" aria-label="Decrease value" onClick={() => adjust(-1)}>-</button>
      <input
        className="input mono text-center"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        inputMode={decimals ? 'decimal' : 'numeric'}
      />
      <button type="button" className="btn-ghost !px-3" aria-label="Increase value" onClick={() => adjust(1)}>+</button>
    </div>
  );
}
