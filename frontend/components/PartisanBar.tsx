
interface PartisanBarProps {
  colorado: number;
  neutro: number;
  anticolorado: number;
}

export default function PartisanBar({
  colorado,
  neutro,
  anticolorado,
}: PartisanBarProps) {
  const values = [
    
   
    {
      label: "Crítico",
      value: anticolorado,
      color: "#2e4c8c",
      text: "#FFFFFF",
    },
     {
      label: "Neutro",
      value: neutro,
      color: "#ffffff",
      text: "#202020",
    },
    {
      label: "Pro",
      value: colorado,
      color: "#fa2d1a",
      text: "#FFFFFF",
    },
  ];

  const total = values.reduce(
    (sum, item) => sum + item.value,
    0
  );

  if (total <= 0) {
    return (
      <p className="text-sm text-gray-500">
        Sin datos de clasificación
      </p>
    );
  }

  return (
    <div
      className="flex h-8 w-full overflow-hidden rounded-sm"
      role="img"
      aria-label={values
        .map((item) => `${item.label}: ${item.value.toFixed(1)}%`)
        .join(", ")}
    >
      {values.map((item) => (
        <div
          key={item.label}
          style={{
            width: `${(item.value / total) * 100}%`,
            backgroundColor: item.color,
            color: item.text,
          }}
          className="flex items-center justify-center overflow-hidden whitespace-nowrap text-xs font-semibold"
          title={`${item.label}: ${item.value.toFixed(1)}%`}
        >
          {item.value / total >= 0.14 &&
            `${item.label} ${Math.round(item.value)}%`}
        </div>
      ))}
    </div>
  );
}
