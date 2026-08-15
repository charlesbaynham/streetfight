// Admin "Identity overrides" page.
//
// Players wear a colour code (backend/identity/) that says who they are from
// a distance. Real guests show up in the wrong clothes, so an admin can
// override individual channels here. Overrides erode the distance guarantee
// that makes the code work at all, so this page is deliberately loud about
// them: the whole point is social pressure to use as few as possible.

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { sendAPIRequest } from "./utils";

import styles from "./AdminIdentity.module.css";

const OUTSIDE_PALETTE = "__outside_palette__";
const AS_ASSIGNED = "__as_assigned__";

const LEVEL_RANK = { critical: 0, danger: 1, warning: 2 };

const LEVEL_MESSAGE = {
  critical: "identical outfits",
  danger: "a single misread confuses them",
  warning: "detection only, no correction",
};

async function postJSON(endpoint, body) {
  const response = await sendAPIRequest(endpoint, null, "POST", null, body);
  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }
  if (!response.ok) {
    if (response.status === 403) {
      throw new Error("Not logged in as admin - go to /admin/login first");
    }
    const detail = data && data.detail;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail || data),
    );
  }
  return data;
}

async function getJSON(endpoint, query_params) {
  const response = await sendAPIRequest(endpoint, query_params, "GET");
  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }
  if (!response.ok) {
    const detail = data && data.detail;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail || data),
    );
  }
  return data;
}

function hexFor(channels, channelName, label) {
  if (!label) return null;
  const channel = channels.find((c) => c.name === channelName);
  return (channel && channel.hex[label]) || null;
}

function distanceDescription(distance, closestPlayers) {
  const names = (closestPlayers || []).map((p) => p.name).join(", ") || null;
  if (distance >= 3) return "full guarantee";
  if (distance === 2) return "one misread is detectable but not correctable";
  if (distance === 1) return `one misread from ${names || "another player"}`;
  return `identical to ${names || "another player"}`;
}

function worstPair(pairs) {
  if (!pairs || pairs.length === 0) return null;
  return [...pairs].sort((a, b) => {
    const rankDiff = LEVEL_RANK[a.level] - LEVEL_RANK[b.level];
    if (rankDiff !== 0) return rankDiff;
    return a.distance - b.distance;
  })[0];
}

// A single colour swatch. Unknown / outside-palette shows as a hatched "?"
// square rather than being silently dropped.
function Swatch({ hex, label, small }) {
  const className = [
    styles.swatch,
    small ? styles.swatchSmall : "",
    hex ? "" : styles.swatchUnknown,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span
      className={className}
      style={hex ? { background: hex } : undefined}
      title={label || "not in palette"}
    >
      {hex ? "" : "?"}
    </span>
  );
}

// One channel's cell in the player table: the effective (worn) colour, with
// a small corner dot showing the canonical colour underneath when the two
// differ, so an override is visible at a glance without opening the editor.
function ChannelSwatch({
  channels,
  channelName,
  canonical,
  effective,
  isOverridden,
}) {
  const effHex = hexFor(channels, channelName, effective);
  const canHex = hexFor(channels, channelName, canonical);

  return (
    <span
      className={styles.channelSwatch}
      title={`${channelName}: ${effective || "not in palette"}${
        isOverridden ? ` (canonical: ${canonical || "not in palette"})` : ""
      }`}
    >
      <Swatch hex={effHex} label={effective} />
      {isOverridden ? (
        <span
          className={styles.canonicalDot}
          style={canHex ? { background: canHex } : undefined}
        />
      ) : null}
    </span>
  );
}

function SummaryStrip({ report }) {
  const overriddenCount = report.players.filter((p) => p.overridden).length;
  const worst = worstPair(report.pairs);
  const tone = worst ? worst.level : "good";

  const toneClass = {
    good: styles.toneGood,
    warning: styles.toneWarning,
    danger: styles.toneDanger,
    critical: styles.toneCritical,
  }[tone];

  return (
    <div className={`${styles.summaryStrip} ${toneClass}`}>
      <div className={styles.summaryStat}>
        <div className={styles.summaryValue}>{report.nominal_min_distance}</div>
        <div className={styles.summaryLabel}>nominal min distance</div>
      </div>
      <div className={styles.summaryStat}>
        <div className={styles.summaryValue}>
          {report.effective_min_distance === null
            ? report.nominal_min_distance
            : report.effective_min_distance}
        </div>
        <div className={styles.summaryLabel}>effective min distance</div>
      </div>
      <div className={styles.summaryStat}>
        <div className={styles.summaryValue}>{overriddenCount}</div>
        <div className={styles.summaryLabel}>
          player{overriddenCount === 1 ? "" : "s"} overridden
        </div>
      </div>
      <div className={styles.summaryHeadline}>
        {worst
          ? `Worst pair: ${worst.name_a} ↔ ${worst.name_b} — ${LEVEL_MESSAGE[worst.level]}`
          : "Full guarantee — no overrides degrade distinguishability."}
      </div>
    </div>
  );
}

function WarningsList({ pairs }) {
  if (!pairs || pairs.length === 0) return null;

  const sorted = [...pairs].sort((a, b) => {
    const rankDiff = LEVEL_RANK[a.level] - LEVEL_RANK[b.level];
    if (rankDiff !== 0) return rankDiff;
    return a.distance - b.distance;
  });

  return (
    <ul className={styles.warningsList}>
      {sorted.map((pair, idx) => (
        <li
          key={idx}
          className={`${styles.warningItem} ${
            {
              warning: styles.toneWarning,
              danger: styles.toneDanger,
              critical: styles.toneCritical,
            }[pair.level]
          }`}
        >
          <b>
            {pair.name_a} ↔ {pair.name_b}
          </b>
          : {LEVEL_MESSAGE[pair.level]}
        </li>
      ))}
    </ul>
  );
}

// Fixed/free suggestion tool: "what colour do I give them?". Fixed channels
// default to whatever the player currently, actually wears; free channels
// (armbands by default) are the ones being solved for.
function SuggestPanel({ gameId, player, channels, onApplied }) {
  const channelNames = useMemo(() => channels.map((c) => c.name), [channels]);

  const [freeChannels, setFreeChannels] = useState(["armbands"]);
  const [fixedValues, setFixedValues] = useState({});
  const [suggestions, setSuggestions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [applyError, setApplyError] = useState(null);
  const [applyForce, setApplyForce] = useState(false);
  const [applyingIdx, setApplyingIdx] = useState(null);

  useEffect(() => {
    const effective = player.effective_appearance || {};
    const initial = {};
    channelNames.forEach((name) => {
      initial[name] = effective[name] || OUTSIDE_PALETTE;
    });
    setFixedValues(initial);
    setSuggestions(null);
    setError(null);
    setApplyError(null);
    // Armbands are the usual thing handed out to a misdressed guest.
    setFreeChannels(["armbands"].filter((n) => channelNames.includes(n)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [player.user_id, channelNames.join(",")]);

  const toggleFree = (name) => {
    setFreeChannels((old) =>
      old.includes(name) ? old.filter((n) => n !== name) : [...old, name],
    );
  };

  const runSuggest = async () => {
    setLoading(true);
    setError(null);
    try {
      const fixed = {};
      channelNames.forEach((name) => {
        if (freeChannels.includes(name)) return;
        const value = fixedValues[name];
        fixed[name] = value === OUTSIDE_PALETTE ? null : value;
      });
      const data = await postJSON("admin_identity_suggest", {
        game_id: gameId,
        user_id: player.user_id,
        fixed,
        free: freeChannels,
      });
      setSuggestions(data.suggestions);
    } catch (e) {
      setSuggestions(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const apply = async (suggestion, idx, force) => {
    setApplyingIdx(idx);
    setApplyError(null);
    try {
      await postJSON("admin_identity_set", {
        user_id: player.user_id,
        slot: suggestion.slot,
        overrides: suggestion.overrides,
        force,
      });
      setApplyForce(false);
      onApplied();
    } catch (e) {
      setApplyError(e.message);
    } finally {
      setApplyingIdx(null);
    }
  };

  return (
    <div className={styles.suggestPanel}>
      <h4>What colour do I give them?</h4>
      <p className={styles.hint}>
        Pick which channels are free to solve for (armbands by default -
        cheapest to hand out); everything else is treated as fixed to what they
        currently wear (or set it below).
      </p>

      <div className={styles.channelFixedGrid}>
        {channels.map((channel) => {
          const isFree = freeChannels.includes(channel.name);
          return (
            <div key={channel.name} className={styles.channelFixedRow}>
              <label className={styles.freeCheckbox}>
                <input
                  type="checkbox"
                  checked={isFree}
                  onChange={() => toggleFree(channel.name)}
                />{" "}
                {channel.name} free
              </label>
              {!isFree ? (
                <select
                  value={fixedValues[channel.name] || OUTSIDE_PALETTE}
                  onChange={(e) =>
                    setFixedValues({
                      ...fixedValues,
                      [channel.name]: e.target.value,
                    })
                  }
                >
                  <option value={OUTSIDE_PALETTE}>not in palette</option>
                  {channel.labels.map((label) => (
                    <option key={label} value={label}>
                      {label}
                    </option>
                  ))}
                </select>
              ) : (
                <span className={styles.hint}>will be chosen</span>
              )}
            </div>
          );
        })}
      </div>

      <button
        onClick={runSuggest}
        disabled={loading || freeChannels.length === 0}
      >
        {loading ? "Thinking..." : "Suggest"}
      </button>
      {freeChannels.length === 0 ? (
        <p className={styles.hint}>Free at least one channel first.</p>
      ) : null}
      {error ? <p className={styles.errorText}>{error}</p> : null}

      {suggestions && suggestions.length === 0 ? (
        <p>No suggestions came back - every combination is already taken.</p>
      ) : null}

      {suggestions && suggestions.length > 0 ? (
        <ul className={styles.suggestionList}>
          {suggestions.map((suggestion, idx) => (
            <li key={idx} className={styles.suggestionCard}>
              <div className={styles.suggestionSwatches}>
                {Object.entries(suggestion.assignment).map(([name, label]) => (
                  <span key={name} className={styles.channelSwatch}>
                    <Swatch hex={hexFor(channels, name, label)} label={label} />
                    <span className={styles.suggestionLabel}>
                      {name}: {label}
                    </span>
                  </span>
                ))}
              </div>
              <div>
                <b>d = {suggestion.min_distance}</b> &mdash;{" "}
                {distanceDescription(
                  suggestion.min_distance,
                  suggestion.closest_players,
                )}
              </div>
              <button
                onClick={() => apply(suggestion, idx, applyForce)}
                disabled={applyingIdx === idx}
              >
                {applyingIdx === idx ? "Applying..." : "Apply"}
              </button>
              {applyError && applyingIdx === null ? (
                <div className={styles.errorBox}>
                  <p className={styles.errorText}>{applyError}</p>
                  <label>
                    <input
                      type="checkbox"
                      checked={applyForce}
                      onChange={(e) => setApplyForce(e.target.checked)}
                    />{" "}
                    Force (apply despite the collision)
                  </label>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function PlayerEditor({
  gameId,
  player,
  channels,
  freeSlots,
  onSaved,
  onClose,
}) {
  const [selectedSlot, setSelectedSlot] = useState("");
  const [channelOverrides, setChannelOverrides] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [force, setForce] = useState(false);

  useEffect(() => {
    setSelectedSlot(player.slot === null ? "" : String(player.slot));
    const initial = {};
    channels.forEach((channel) => {
      const overrides = player.overrides || {};
      if (channel.name in overrides) {
        const value = overrides[channel.name];
        initial[channel.name] = value === null ? OUTSIDE_PALETTE : value;
      } else {
        initial[channel.name] = AS_ASSIGNED;
      }
    });
    setChannelOverrides(initial);
    setSaveError(null);
    setForce(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [player.user_id]);

  const slotOptions = useMemo(() => {
    const options = new Set(freeSlots || []);
    if (player.slot !== null) options.add(player.slot);
    return [...options].sort((a, b) => a - b);
  }, [freeSlots, player.slot]);

  const save = async (forceValue) => {
    setSaving(true);
    setSaveError(null);
    try {
      const overridesPayload = {};
      let anyOverride = false;
      Object.entries(channelOverrides).forEach(([channel, value]) => {
        if (value === AS_ASSIGNED) return;
        anyOverride = true;
        overridesPayload[channel] = value === OUTSIDE_PALETTE ? null : value;
      });

      const updated = await postJSON("admin_identity_set", {
        user_id: player.user_id,
        slot: selectedSlot === "" ? null : parseInt(selectedSlot, 10),
        overrides: anyOverride ? overridesPayload : null,
        force: forceValue,
      });
      setForce(false);
      onSaved(updated);
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.editor}>
      <div className={styles.editorHeader}>
        <h3>
          {player.name} <small>({player.team_name})</small>
        </h3>
        <button onClick={onClose}>Close</button>
      </div>

      <div className={styles.editorField}>
        <label>
          Slot:{" "}
          <select
            value={selectedSlot}
            onChange={(e) => setSelectedSlot(e.target.value)}
          >
            <option value="">none</option>
            {slotOptions.map((slot) => (
              <option key={slot} value={slot}>
                {slot}
                {player.slot === slot ? " (current)" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>

      <table className={styles.overrideTable}>
        <thead>
          <tr>
            <th>channel</th>
            <th>as assigned</th>
            <th>override</th>
          </tr>
        </thead>
        <tbody>
          {channels.map((channel) => {
            const canonical =
              player.canonical_appearance &&
              player.canonical_appearance[channel.name];
            return (
              <tr key={channel.name}>
                <td>{channel.name}</td>
                <td>
                  <Swatch
                    hex={hexFor(channels, channel.name, canonical)}
                    label={canonical}
                    small
                  />{" "}
                  {canonical || <i>no slot</i>}
                </td>
                <td>
                  <select
                    value={channelOverrides[channel.name] || AS_ASSIGNED}
                    onChange={(e) =>
                      setChannelOverrides({
                        ...channelOverrides,
                        [channel.name]: e.target.value,
                      })
                    }
                  >
                    <option value={AS_ASSIGNED}>as assigned</option>
                    <option value={OUTSIDE_PALETTE}>not in palette</option>
                    {channel.labels.map((label) => (
                      <option key={label} value={label}>
                        {label}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <button onClick={() => save(force)} disabled={saving}>
        {saving ? "Saving..." : "Save"}
      </button>

      {saveError ? (
        <div className={styles.errorBox}>
          <p className={styles.errorText}>{saveError}</p>
          <label>
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
            />{" "}
            Force (apply despite the collision)
          </label>
        </div>
      ) : null}

      <SuggestPanel
        gameId={gameId}
        player={player}
        channels={channels}
        onApplied={() => onSaved(null)}
      />
    </div>
  );
}

function PlayerTable({ report, selectedId, onSelect }) {
  const channels = report.channels;

  return (
    <div className={styles.tableWrap}>
      <table className={styles.playerTable}>
        <thead>
          <tr>
            <th>name</th>
            <th>team</th>
            <th>slot</th>
            <th>outfit</th>
          </tr>
        </thead>
        <tbody>
          {report.players.map((player) => (
            <tr
              key={player.user_id}
              className={[
                styles.playerRow,
                player.overridden ? styles.overriddenRow : "",
                player.user_id === selectedId ? styles.selectedRow : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => onSelect(player.user_id)}
            >
              <td>
                {player.name}
                {player.overridden ? (
                  <span className={styles.overrideBadge}>override</span>
                ) : null}
              </td>
              <td>{player.team_name}</td>
              <td>
                {player.slot === null ? (
                  <span className={styles.hint}>none</span>
                ) : (
                  player.slot
                )}
              </td>
              <td>
                <div className={styles.swatchRow}>
                  {channels.map((channel) => (
                    <ChannelSwatch
                      key={channel.name}
                      channels={channels}
                      channelName={channel.name}
                      canonical={
                        player.canonical_appearance
                          ? player.canonical_appearance[channel.name]
                          : null
                      }
                      effective={
                        player.effective_appearance
                          ? player.effective_appearance[channel.name]
                          : null
                      }
                      isOverridden={
                        !!(player.overrides && channel.name in player.overrides)
                      }
                    />
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GameSelector({ games, gameId, setGameId }) {
  if (games.length <= 1) return null;

  return (
    <p>
      <label>
        Game:{" "}
        <select
          value={gameId || ""}
          onChange={(e) => setGameId(e.target.value)}
        >
          {games.map((game) => (
            <option key={game.id} value={game.id}>
              {game.id.slice(0, 8)} (
              {game.teams.map((t) => t.name).join(", ") || "no teams"})
            </option>
          ))}
        </select>
      </label>
    </p>
  );
}

export default function AdminIdentity() {
  const [games, setGames] = useState(null);
  const [gameId, setGameId] = useState(null);
  const [report, setReport] = useState(null);
  const [reportError, setReportError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    sendAPIRequest("admin_list_games", null, "GET", (loadedGames) => {
      setGames(loadedGames);
      if (loadedGames.length > 0 && !gameId) {
        setGameId(loadedGames[0].id);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadReport = useCallback(async () => {
    if (!gameId) return;
    setLoading(true);
    setReportError(null);
    try {
      const data = await getJSON("admin_identity_report", { game_id: gameId });
      setReport(data);
    } catch (e) {
      setReport(null);
      setReportError(e.message);
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const handleSaved = useCallback(
    (updatedPlayer) => {
      // Reload the whole report: an override to one player can change pairs
      // involving other players too.
      loadReport();
      if (updatedPlayer) setSelectedId(updatedPlayer.user_id);
    },
    [loadReport],
  );

  if (games === null) return <p>Loading games...</p>;
  if (games.length === 0) return <p>No games exist yet - create one first.</p>;

  const selectedPlayer =
    report && selectedId
      ? report.players.find((p) => p.user_id === selectedId)
      : null;

  return (
    <div>
      <h1>Identity overrides</h1>
      <p className={styles.hint}>
        Every override erodes the guarantee that the colour code identifies
        players unambiguously - keep them rare.
      </p>

      <GameSelector games={games} gameId={gameId} setGameId={setGameId} />

      {loading && !report ? <p>Loading report...</p> : null}
      {reportError ? <p className={styles.errorText}>{reportError}</p> : null}

      {report ? (
        <>
          <SummaryStrip report={report} />
          <WarningsList pairs={report.pairs} />
          <PlayerTable
            report={report}
            selectedId={selectedId}
            onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
          />

          {selectedPlayer ? (
            <PlayerEditor
              gameId={gameId}
              player={selectedPlayer}
              channels={report.channels}
              freeSlots={report.free_slots}
              onSaved={handleSaved}
              onClose={() => setSelectedId(null)}
            />
          ) : (
            <p className={styles.hint}>
              Tap a player to see and override their outfit.
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}
