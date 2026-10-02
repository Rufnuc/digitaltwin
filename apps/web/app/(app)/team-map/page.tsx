"use client";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Card } from "@/components/ui";
import { LocationMap } from "@/components/LocationMap";
import { api, type UserLocationLatest, type UserLocationPoint } from "@/lib/api";

export default function TeamMapPage() {
  const [people, setPeople] = useState<UserLocationLatest[]>([]);
  const [trail, setTrail] = useState<UserLocationPoint[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.locationsLatest();
      setPeople(r.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load locations");
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000); // refresh pins every 30s
    return () => clearInterval(t);
  }, [load]);

  const showTrail = useCallback(async (userId: number) => {
    setSelected(userId);
    try {
      const r = await api.locationHistory(userId);
      setTrail(r.items);
    } catch {
      setTrail([]);
    }
  }, []);

  const selectedName = people.find((p) => p.user_id === selected)?.user_name;

  return (
    <div>
      <PageHeader
        title="Team Map"
        subtitle="Where each team member was last seen while logged in on a company device. Click a person to see their recent movement trail. Location changes are recorded in the Activity Log."
      />

      {error && <div className="mb-3 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_260px]">
        <LocationMap people={people} trail={trail} onSelect={showTrail} />

        <Card className="p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">Team ({people.length})</span>
            {selected && (
              <button
                onClick={() => {
                  setSelected(null);
                  setTrail([]);
                }}
                className="text-[11px] text-muted underline decoration-dotted"
              >
                clear trail
              </button>
            )}
          </div>
          {people.length === 0 ? (
            <div className="text-xs text-muted">
              No locations yet. Team members are tracked once they log in on a device that
              has granted location permission.
            </div>
          ) : (
            <ul className="space-y-1">
              {people.map((p) => (
                <li key={p.user_id}>
                  <button
                    onClick={() => showTrail(p.user_id)}
                    className={`w-full rounded border px-2 py-1.5 text-left text-sm hover:bg-wash ${
                      selected === p.user_id ? "border-ink" : "border-line"
                    }`}
                  >
                    <div className="font-medium">{p.user_name}</div>
                    <div className="text-[11px] text-muted">
                      {p.role}
                      {p.recorded_at
                        ? ` · ${new Date(p.recorded_at).toLocaleString("en-NG", { dateStyle: "short", timeStyle: "short" })}`
                        : ""}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {selected && (
            <div className="mt-2 text-[11px] text-muted">
              Showing {trail.length} recent points for {selectedName}.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
