// Classic mode's round avatar: the employee's avatar image if they have one, otherwise their initials.
import { accentFor } from "../art/looks";
import { initials, textColorFor } from "./avatarText";

interface Props {
  roleId: string;
  name: string;
  src?: string | null;
  size?: number;
  className?: string;
}

export function Avatar({ roleId, name, src, size = 40, className = "" }: Props) {
  const bg = accentFor(roleId);
  return (
    <span
      className={`avatar ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38), background: bg, color: textColorFor(bg) }}
      aria-hidden
    >
      {src ? <img src={src} alt="" /> : initials(name)}
    </span>
  );
}
