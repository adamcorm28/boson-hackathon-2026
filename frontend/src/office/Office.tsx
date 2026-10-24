// The office floor: tiles, desks with their employees, and you. Thin rendering over map.ts/movement.ts.
import { useEffect, useMemo, useRef, useState } from "react";
import type { Role } from "../api/types";
import { lookFor, PLAYER_LOOK } from "../art/looks";
import { Sprite } from "../art/Sprite";
import { layoutDesks, MAP_HEIGHT, MAP_WIDTH, OFFICE_MAP, START, type Pos } from "./map";
import { distance, nearby, step, type Dir } from "./movement";

export const TILE = 32;
const STEP_MS = 130; // walking speed while a key is held
const HANG_UP_DISTANCE = 2;

const KEY_DIRS: Record<string, Dir> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  w: "up",
  s: "down",
  a: "left",
  d: "right",
};

const TILE_CLASS: Record<string, string> = { "#": "wall", ".": "floor", D: "door", W: "board", R: "rug" };

interface Props {
  roles: Role[];
  /** The role on the line, while a call is connecting or live. */
  activeRoleId: string | null;
  onDial(roleId: string): void;
  onHangup(): void;
  onOpenBoard(): void;
  /** Ignore the keyboard (e.g. while the whiteboard is open). */
  paused?: boolean;
}

const firstName = (r?: Role) => r?.name.split(" ")[0] ?? "";

export function Office({ roles, activeRoleId, onDial, onHangup, onOpenBoard, paused = false }: Props) {
  const desks = useMemo(() => layoutDesks(roles), [roles]);
  const [pos, setPos] = useState<Pos>(START);
  const [stepping, setStepping] = useState(false);
  const posRef = useRef(pos);
  posRef.current = pos;

  // Latest props for the key handlers, which are registered once.
  const live = useRef({ desks, paused, onDial, onOpenBoard });
  live.current = { desks, paused, onDial, onOpenBoard };

  useEffect(() => {
    const held: Dir[] = [];
    let timer: ReturnType<typeof setInterval> | null = null;

    const move = () => {
      const dir = held.at(-1);
      if (!dir) return;
      const next = step(posRef.current, dir, live.current.desks);
      if (next !== posRef.current) {
        posRef.current = next;
        setPos(next);
        setStepping((s) => !s);
      }
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (live.current.paused || e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const dir = KEY_DIRS[key];
      if (dir) {
        e.preventDefault(); // no page scrolling
        if (e.repeat) return; // our own timer handles held keys
        const i = held.indexOf(dir);
        if (i >= 0) held.splice(i, 1);
        held.push(dir); // the most recent key wins
        move();
        timer ??= setInterval(move, STEP_MS);
        return;
      }
      if (key === "e" && !e.repeat) {
        const near = nearby(posRef.current, live.current.desks);
        if (near?.kind === "desk") live.current.onDial(near.roleId);
        else if (near?.kind === "board") live.current.onOpenBoard();
      } else if (key === "b" && !e.repeat) {
        live.current.onOpenBoard();
      }
    };

    const onKeyUp = (e: KeyboardEvent) => {
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const dir = KEY_DIRS[key];
      if (!dir) return;
      const i = held.indexOf(dir);
      if (i >= 0) held.splice(i, 1);
      if (held.length === 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    };

    const stopAll = () => {
      held.length = 0;
      if (timer) clearInterval(timer);
      timer = null;
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", stopAll); // don't keep walking after alt-tab
    return () => {
      stopAll();
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", stopAll);
    };
  }, []);

  // Walking away from the desk hangs up.
  const onHangupRef = useRef(onHangup);
  onHangupRef.current = onHangup;
  useEffect(() => {
    if (!activeRoleId) return;
    const desk = desks.find((d) => d.roleId === activeRoleId);
    if (desk && distance(pos, desk) > HANG_UP_DISTANCE) onHangupRef.current();
  }, [pos, activeRoleId, desks]);

  const near = nearby(pos, desks);
  const nearRole = near?.kind === "desk" ? roles.find((r) => r.id === near.roleId) : undefined;
  let hint = "Walk up to someone's desk to call them";
  if (near?.kind === "desk") hint = activeRoleId === near.roleId ? `On a call with ${firstName(nearRole)}` : `E: call ${firstName(nearRole).toUpperCase()}`;
  else if (near?.kind === "board") hint = "E: open the whiteboard";

  return (
    <div className="office-wrap">
      <div className="office" style={{ width: MAP_WIDTH * TILE, height: MAP_HEIGHT * TILE }}>
        {OFFICE_MAP.flatMap((row, y) =>
          [...row].map((c, x) => (
            <div key={`${x},${y}`} className={`tile ${TILE_CLASS[c] ?? "floor"}`} style={{ left: x * TILE, top: y * TILE }} />
          )),
        )}

        {desks.map((d) => {
          const role = roles.find((r) => r.id === d.roleId);
          const onCall = activeRoleId === d.roleId;
          const isNear = near?.kind === "desk" && near.roleId === d.roleId;
          return (
            <div key={d.roleId}>
              <div
                className={`employee ${onCall ? "on-call" : ""}`}
                style={{ left: d.x * TILE + 1, top: d.y * TILE - 30, zIndex: d.y * 10 + 1 }}
              >
                {(isNear || onCall) && <div className="nameplate">{firstName(role)}</div>}
                <Sprite look={lookFor(d.roleId)} />
              </div>
              <div className="desk" style={{ left: d.x * TILE, top: d.y * TILE, zIndex: d.y * 10 + 2 }}>
                <div className="monitor" />
              </div>
            </div>
          );
        })}

        <div className="player" style={{ left: pos.x * TILE + 1, top: pos.y * TILE - 12, zIndex: pos.y * 10 + 5 }}>
          <Sprite look={PLAYER_LOOK} stepping={stepping} />
        </div>
      </div>

      <div className="keybar">
        <span className="hint">{hint}</span>
        <span className="muted">←↑↓→/WASD move · E call · Esc hang up · B board</span>
      </div>
    </div>
  );
}
