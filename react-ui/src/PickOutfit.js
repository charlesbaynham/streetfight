// The outfit-picking page a player lands on after scanning a *team* join
// code (as opposed to a per-slot code, which still claims a fixed outfit
// straight away - see JoinFromQueryParams). They declare what they own, are
// offered a ranked list of outfits that are both wearable and distinguishable
// from everyone already placed, and pick one. See
// docs/pick_your_colours_plan.md ("The design" and "C7") for the full
// rationale behind the ranking and the flow below.
//
// Deliberately outside UserMode: no map, no webcam, no SSE, no permission
// polling - this page only ever talks to join_options / outfit_options /
// pick_outfit.

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

import Popup from "./Popup";
import { sendAPIRequest } from "./utils";
import { NameEntry } from "./OnboardingView";
import { Swatch, hexFor } from "./Swatch";

import styles from "./PickOutfit.module.css";

// Same idiom as JoinFromQueryParams.useQuery - this page is mounted at its
// own flat route, not underneath it, so it needs its own copy.
function useQuery() {
  const { search } = useLocation();
  return React.useMemo(() => new URLSearchParams(search), [search]);
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
    const err = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail || data),
    );
    err.status = response.status;
    throw err;
  }
  return data;
}

async function postJSON(endpoint, body) {
  const response = await sendAPIRequest(endpoint, null, "POST", null, body);
  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }
  if (!response.ok) {
    const detail = data && data.detail;
    const err = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail || data),
    );
    err.status = response.status;
    throw err;
  }
  return data;
}

function Header({ joinData }) {
  const hex = hexFor(
    joinData.channels,
    joinData.team_channel,
    joinData.team_colour,
  );
  return (
    <div className={styles.header}>
      <h1>Team {joinData.team_name}</h1>
      <Swatch hex={hex} label={joinData.team_colour} size="large" />
      <p>
        We're bringing your {joinData.team_colour} {joinData.team_channel} and
        your {joinData.provided_channel}. Tell us what you'll wear underneath.
      </p>
    </div>
  );
}

function WardrobeChannel({ channel, selected, colourNotes, onToggle }) {
  return (
    <fieldset className={styles.wardrobeChannel}>
      <legend>{channel.name}</legend>
      <div className={styles.swatchGrid}>
        {channel.labels.map((label) => {
          const isSelected = selected.includes(label);
          const note = colourNotes[label];
          return (
            <button
              type="button"
              key={label}
              className={
                styles.swatchButton +
                (isSelected ? " " + styles.swatchSelected : "")
              }
              aria-pressed={isSelected}
              aria-label={label}
              onClick={() => onToggle(label)}
            >
              <Swatch hex={channel.hex[label]} label={label} size="large" />
              <span className={styles.swatchLabel}>{label}</span>
              {note ? <span className={styles.swatchNote}>{note}</span> : null}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function optionDescription(option) {
  return Object.entries(option.appearance)
    .map(([name, label]) => `${name} ${label}`)
    .join(", ");
}

function OptionRow({ option, channels, oursChannels, onPick }) {
  return (
    <button
      type="button"
      className={styles.optionRow}
      aria-label={`Choose: ${optionDescription(option)}`}
      onClick={() => onPick(option)}
    >
      {option.is_canonical ? (
        <span className={styles.recommendedBadge}>recommended</span>
      ) : null}
      <div className={styles.optionGarments}>
        {channels.map((channel) => {
          const label = option.appearance[channel.name];
          return (
            <span key={channel.name} className={styles.garment}>
              <Swatch hex={channel.hex[label]} label={label} />
              <span className={styles.garmentLabel}>
                {channel.name}: {label}
                <span className={styles.tag}>
                  {oursChannels.includes(channel.name) ? "ours" : "yours"}
                </span>
              </span>
            </span>
          );
        })}
      </div>
    </button>
  );
}

// Options arrive from the backend already sorted by overrides_needed, so a
// simple linear scan groups consecutive equal values without re-sorting.
function OptionsList({ options, channels, oursChannels, onPick }) {
  let lastOverrides = null;
  return (
    <div className={styles.optionsList}>
      {options.map((option) => {
        const showHeading = option.overrides_needed !== lastOverrides;
        lastOverrides = option.overrides_needed;
        return (
          <React.Fragment key={optionDescription(option)}>
            {showHeading ? (
              <h3 className={styles.groupHeading}>
                {option.overrides_needed === 0
                  ? "Exact match"
                  : `${option.overrides_needed} colour${
                      option.overrides_needed === 1 ? "" : "s"
                    } different`}
              </h3>
            ) : null}
            <OptionRow
              option={option}
              channels={channels}
              oursChannels={oursChannels}
              onPick={onPick}
            />
          </React.Fragment>
        );
      })}
    </div>
  );
}

function ResultScreen({ appearance, channels }) {
  return (
    <div className={styles.resultScreen}>
      <h2>You're set</h2>
      <div className={styles.resultGarments}>
        {channels.map((channel) => {
          const label = appearance ? appearance[channel.name] : null;
          return (
            <div key={channel.name} className={styles.resultGarment}>
              <Swatch hex={channel.hex[label]} label={label} size="large" />
              <div>
                <div className={styles.resultChannelName}>{channel.name}</div>
                <div>{label}</div>
              </div>
            </div>
          );
        })}
      </div>
      <p className={styles.finalNote}>This is final. Screenshot it.</p>
    </div>
  );
}

function PickOutfitForm({ code, joinData, onPicked, onError }) {
  const [wardrobe, setWardrobe] = useState({});
  const [confirmed, setConfirmed] = useState(false);
  const [optionsResult, setOptionsResult] = useState(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [claiming, setClaiming] = useState(false);

  const oursChannels = useMemo(
    () => [joinData.team_channel, joinData.provided_channel],
    [joinData.team_channel, joinData.provided_channel],
  );

  const toggleColour = (channelName, label) => {
    setWardrobe((old) => {
      const current = old[channelName] || [];
      const next = current.includes(label)
        ? current.filter((l) => l !== label)
        : [...current, label];
      return { ...old, [channelName]: next };
    });
    setOptionsResult(null);
  };

  const fetchOptions = useCallback(
    async (relaxed, page) => {
      setOptionsLoading(true);
      try {
        const result = await postJSON("outfit_options", {
          data: code,
          wardrobe,
          relaxed,
          page,
        });
        setOptionsResult(result);
      } catch (e) {
        onError(e.message);
      } finally {
        setOptionsLoading(false);
      }
    },
    [code, wardrobe, onError],
  );

  const claimOption = useCallback(
    async (option) => {
      setClaiming(true);
      try {
        const row = await postJSON("pick_outfit", {
          data: code,
          wardrobe,
          appearance: option.appearance,
          confirmed: true,
        });
        onPicked(row);
      } catch (e) {
        onError(e.message);
        if (e.status === 409 && optionsResult) {
          fetchOptions(optionsResult.relaxed, optionsResult.page);
        }
      } finally {
        setClaiming(false);
      }
    },
    [code, wardrobe, onPicked, onError, optionsResult, fetchOptions],
  );

  const showAreYouSure =
    optionsResult && optionsResult.total === 0 && !optionsResult.relaxed;
  const totalPages = optionsResult
    ? Math.max(1, Math.ceil(optionsResult.total / optionsResult.page_size))
    : 0;

  return (
    <>
      {joinData.you && joinData.you.name ? null : (
        <NameEntry
          user={joinData.you || { name: null }}
          className={styles.nameEntry}
        />
      )}

      <p className={styles.wardrobeIntro}>
        Tick everything you own - the more you tick, the more choices you get.
      </p>

      {joinData.wardrobe_channels.map((channelName) => {
        const channel = joinData.channels.find((c) => c.name === channelName);
        if (!channel) return null;
        return (
          <WardrobeChannel
            key={channelName}
            channel={channel}
            selected={wardrobe[channelName] || []}
            colourNotes={joinData.colour_notes}
            onToggle={(label) => toggleColour(channelName, label)}
          />
        );
      })}

      <label className={styles.confirmRow}>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        I own these and I'll wear them on the night.
      </label>

      <button
        type="button"
        className={styles.submitButton}
        disabled={!confirmed || optionsLoading}
        onClick={() => fetchOptions(false, 0)}
      >
        {optionsLoading ? "Finding outfits..." : "Show me outfits"}
      </button>

      {showAreYouSure ? (
        <div className={styles.emptyState}>
          <p>No outfits found. Are you sure you don't have any more clothes?</p>
          <button type="button" onClick={() => fetchOptions(true, 0)}>
            Yes, I'm sure
          </button>
        </div>
      ) : null}

      {optionsResult && optionsResult.exhausted ? (
        <p className={styles.exhaustedNote}>
          These are the best options we could find - sorry for the limited
          choice.
        </p>
      ) : null}

      {optionsResult && optionsResult.total > 0 ? (
        <>
          <OptionsList
            options={optionsResult.options}
            channels={joinData.channels}
            oursChannels={oursChannels}
            onPick={claimOption}
          />
          {totalPages > 1 ? (
            <div className={styles.pagination}>
              <button
                type="button"
                disabled={optionsResult.page <= 0 || claiming}
                onClick={() =>
                  fetchOptions(optionsResult.relaxed, optionsResult.page - 1)
                }
              >
                Previous
              </button>
              <span>
                Page {optionsResult.page + 1} of {totalPages}
              </span>
              <button
                type="button"
                disabled={optionsResult.page + 1 >= totalPages || claiming}
                onClick={() =>
                  fetchOptions(optionsResult.relaxed, optionsResult.page + 1)
                }
              >
                Next
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </>
  );
}

function PickOutfit() {
  const query = useQuery();
  const code = query.get("j");

  const [joinData, setJoinData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [pickedRow, setPickedRow] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [errorVisible, setErrorVisible] = useState(false);

  useEffect(() => {
    if (!code) return undefined;
    let cancelled = false;
    getJSON("join_options", { data: code })
      .then((data) => {
        if (!cancelled) setJoinData(data);
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  const showError = useCallback((message) => {
    setErrorMessage(message);
    setErrorVisible(true);
  }, []);

  const alreadyPicked =
    joinData &&
    joinData.you &&
    joinData.you.slot !== null &&
    joinData.you.slot !== undefined;
  const result = pickedRow || (alreadyPicked ? joinData.you : null);

  return (
    <div className={styles.outerContainer}>
      <Popup visible={errorVisible} setVisible={setErrorVisible}>
        <p>{errorMessage}</p>
      </Popup>
      <div className={styles.innerContainer}>
        {!code ? (
          <p>No invite link found - ask your team for the join link again.</p>
        ) : loadError ? (
          <p className={styles.errorText}>{loadError}</p>
        ) : !joinData ? (
          <p>Loading...</p>
        ) : (
          <>
            <Header joinData={joinData} />
            {result ? (
              <ResultScreen
                appearance={result.effective_appearance}
                channels={joinData.channels}
              />
            ) : (
              <PickOutfitForm
                code={code}
                joinData={joinData}
                onPicked={setPickedRow}
                onError={showError}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default PickOutfit;
