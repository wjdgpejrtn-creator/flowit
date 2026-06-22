interface SkelProps {
  w?: string;
  h?: number;
  className?: string;
}

export default function Skel({ w = '100%', h = 12, className = '' }: SkelProps) {
  return (
    <div
      className={`rounded animate-shimmer ${className}`}
      style={{ width: w, height: h }}
    />
  );
}
