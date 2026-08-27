// The outfit-picking page a player lands on after scanning a *team* join
// code (as opposed to a per-slot code, which still claims a fixed outfit
// straight away - see JoinFromQueryParams). They declare what they own, are
// offered a ranked list of outfits that are both wearable and distinguishable
// from everyone already placed, pick one, confirm it, and lock it in. See
// docs/roadmap.md's #10 entry and backend/identity_admin.py's outfit_options
// for the ranking rationale behind the flow below.
//
// Deliberately outside UserMode: no map, no webcam, no SSE, no permission
// polling - this page only ever talks to join_options / outfit_options /
// pick_outfit.

import React, { useCallback, useEffect, useState } from "react";
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

// A channel name is only ever a raw scheme identifier ("tshirt", "hat", ...)
// - this is the one place that turns it into something worth showing a
// player. Keyed off the name so a future channel (a "shape" channel, say)
// just falls through to the capitalised default instead of reading raw.
const CHANNEL_DISPLAY_NAMES = { tshirt: "T-shirt" };

function channelLabel(name) {
  return (
    CHANNEL_DISPLAY_NAMES[name] || name.charAt(0).toUpperCase() + name.slice(1)
  );
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

function Header({ joinData, showWardrobePrompt }) {
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
        We'll bring your {joinData.team_colour}{" "}
        {channelLabel(joinData.team_channel).toLowerCase()} and your{" "}
        {channelLabel(joinData.provided_channel).toLowerCase()} on the night.
        {showWardrobePrompt ? " Tell us what else you'll be wearing." : null}
      </p>
    </div>
  );
}

function WardrobeChannel({ channel, selected, colourNotes, onToggle }) {
  return (
    <fieldset className={styles.wardrobeChannel}>
      <legend>{channelLabel(channel.name)}</legend>
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

// Both used to key/label an option by what the player can actually see and
// chose: the wardrobe channels only (roadmap #10 revision) - the hat is
// pinned to the team colour and the armband is ours to assign, so neither is
// a choice the player has a stake in, and the backend now collapses options
// so no two share a wardrobe combination, keeping this a stable React key.
function optionDescription(option, wardrobeChannels) {
  return wardrobeChannels
    .map((name) => `${channelLabel(name)} ${option.appearance[name]}`)
    .join(", ");
}

function OutfitGarments({ appearance, wardrobeChannels, channels, size }) {
  return (
    <div className={styles.optionGarments}>
      {wardrobeChannels.map((name) => {
        const channel = channels.find((c) => c.name === name);
        const label = appearance[name];
        return (
          <span key={name} className={styles.garment}>
            <Swatch hex={channel.hex[label]} label={label} size={size} />
            <span className={styles.garmentLabel}>
              {channelLabel(name)}: {label}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function OptionRow({ option, wardrobeChannels, channels, onPick }) {
  return (
    <button
      type="button"
      className={styles.optionRow}
      aria-label={`Choose: ${optionDescription(option, wardrobeChannels)}`}
      onClick={() => onPick(option)}
    >
      {option.is_canonical ? (
        <span className={styles.recommendedBadge}>recommended</span>
      ) : null}
      <OutfitGarments
        appearance={option.appearance}
        wardrobeChannels={wardrobeChannels}
        channels={channels}
      />
    </button>
  );
}

// Options arrive from the backend already sorted by overrides_needed, so a
// simple linear scan groups consecutive equal values without re-sorting.
function OptionsList({ options, wardrobeChannels, channels, onPick }) {
  let lastOverrides = null;
  return (
    <div className={styles.optionsList}>
      {options.map((option) => {
        const showHeading = option.overrides_needed !== lastOverrides;
        lastOverrides = option.overrides_needed;
        return (
          <React.Fragment key={optionDescription(option, wardrobeChannels)}>
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
              wardrobeChannels={wardrobeChannels}
              channels={channels}
              onPick={onPick}
            />
          </React.Fragment>
        );
      })}
    </div>
  );
}

function WardrobeSummary({ wardrobeChannels, wardrobe, onChange }) {
  const description = wardrobeChannels
    .map((name) => {
      const chosen = wardrobe[name] || [];
      return `${channelLabel(name)}: ${chosen.length ? chosen.join(", ") : "anything"}`;
    })
    .join(" · ");
  return (
    <div className={styles.wardrobeSummary}>
      <p>{description}</p>
      <button type="button" className={styles.linkButton} onClick={onChange}>
        Change what I own
      </button>
    </div>
  );
}

function ConfirmScreen({
  option,
  wardrobeChannels,
  channels,
  onConfirm,
  onBack,
  confirming,
}) {
  const [checked, setChecked] = useState(false);
  return (
    <div className={styles.confirmScreen}>
      <h2>Wear this outfit?</h2>
      <OutfitGarments
        appearance={option.appearance}
        wardrobeChannels={wardrobeChannels}
        channels={channels}
        size="large"
      />
      <label className={styles.confirmRow}>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
        />
        I will wear this on the night.
      </label>
      <button
        type="button"
        className={styles.submitButton}
        disabled={!checked || confirming}
        onClick={onConfirm}
      >
        {confirming ? "Locking in..." : "Lock in my choice"}
      </button>
      <button
        type="button"
        className={styles.linkButton}
        onClick={onBack}
        disabled={confirming}
      >
        Choose a different outfit
      </button>
    </div>
  );
}

function ResultScreen({ appearance, wardrobeChannels, channels }) {
  return (
    <div className={styles.resultScreen}>
      <h2>You're set</h2>
      <div className={styles.resultGarments}>
        {wardrobeChannels.map((name) => {
          const channel = channels.find((c) => c.name === name);
          const label = appearance ? appearance[name] : null;
          return (
            <div key={name} className={styles.resultGarment}>
              <Swatch hex={channel.hex[label]} label={label} size="large" />
              <div>
                <div className={styles.resultChannelName}>
                  {channelLabel(name)}
                </div>
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

function PickOutfitForm({
  code,
  joinData,
  onPicked,
  onError,
  onChoosingChange,
}) {
  const [wardrobe, setWardrobe] = useState({});
  const [optionsResult, setOptionsResult] = useState(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [selectedOption, setSelectedOption] = useState(null);
  const [claiming, setClaiming] = useState(false);
  const [showingAll, setShowingAll] = useState(false);

  // The header's "tell us what else you'll be wearing" prompt is an
  // instruction, and on the confirm screen there is nothing left to tell -
  // the player is being asked to approve a specific outfit. Let the parent,
  // which owns the header, know when we are on that screen.
  useEffect(() => {
    onChoosingChange(selectedOption !== null);
  }, [selectedOption, onChoosingChange]);

  const wardrobeChannels = joinData.wardrobe_channels;

  // Back to the wardrobe form: the next list is a fresh one, so it starts
  // nudging again rather than inheriting a previous "show me the rest".
  const reopenWardrobe = () => {
    setOptionsResult(null);
    setShowingAll(false);
  };

  const toggleColour = (channelName, label) => {
    setWardrobe((old) => {
      const current = old[channelName] || [];
      const next = current.includes(label)
        ? current.filter((l) => l !== label)
        : [...current, label];
      return { ...old, [channelName]: next };
    });
    reopenWardrobe();
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
        setSelectedOption(null);
        if (e.status === 409 && optionsResult) {
          fetchOptions(optionsResult.relaxed, optionsResult.page);
        }
      } finally {
        setClaiming(false);
      }
    },
    [code, wardrobe, onPicked, onError, optionsResult, fetchOptions],
  );

  if (selectedOption) {
    return (
      <ConfirmScreen
        option={selectedOption}
        wardrobeChannels={wardrobeChannels}
        channels={joinData.channels}
        confirming={claiming}
        onConfirm={() => claimOption(selectedOption)}
        onBack={() => setSelectedOption(null)}
      />
    );
  }

  const showAreYouSure =
    optionsResult && optionsResult.total === 0 && !optionsResult.relaxed;
  const showingOptions = optionsResult && optionsResult.total > 0;
  const totalPages = optionsResult
    ? Math.max(1, Math.ceil(optionsResult.total / optionsResult.page_size))
    : 0;

  // Every option is pickable, but the canonical ones are the ones the code
  // is built out of - offering the rest alongside them invites a player to
  // spend identification accuracy on a colour they like the look of. So only
  // the canonical ones are shown until the player asks for the others, which
  // also hides the pagination: a recommended outfit is never more than a tap
  // away, and the long tail takes a deliberate one. When the wardrobe
  // supports no canonical outfit at all there is nothing to nudge towards,
  // so the full list stands as it is rather than leaving an empty page.
  const pageOptions = optionsResult ? optionsResult.options : [];
  const recommendedOptions = pageOptions.filter(
    (option) => option.is_canonical,
  );
  const nudging = !showingAll && recommendedOptions.length > 0;
  const visibleOptions = nudging ? recommendedOptions : pageOptions;
  const hasOthers =
    recommendedOptions.length < pageOptions.length || totalPages > 1;

  return (
    <>
      {joinData.you && joinData.you.name ? null : (
        <NameEntry
          user={joinData.you || { name: null }}
          className={styles.nameEntry}
        />
      )}

      {showingOptions ? (
        <WardrobeSummary
          wardrobeChannels={wardrobeChannels}
          wardrobe={wardrobe}
          onChange={reopenWardrobe}
        />
      ) : (
        <>
          <p className={styles.wardrobeIntro}>
            Tick everything you own - the more you tick, the more choices you
            get.
          </p>

          {wardrobeChannels.map((channelName) => {
            const channel = joinData.channels.find(
              (c) => c.name === channelName,
            );
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

          <button
            type="button"
            className={styles.submitButton}
            disabled={optionsLoading}
            onClick={() => fetchOptions(false, 0)}
          >
            {optionsLoading ? "Finding outfits..." : "Show me outfits"}
          </button>
        </>
      )}

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

      {showingOptions ? (
        <>
          <OptionsList
            options={visibleOptions}
            wardrobeChannels={wardrobeChannels}
            channels={joinData.channels}
            onPick={setSelectedOption}
          />
          {nudging && hasOthers ? (
            <button
              type="button"
              className={styles.linkButton}
              onClick={() => setShowingAll(true)}
            >
              Show non-recommended outfits
            </button>
          ) : null}
          {!nudging && totalPages > 1 ? (
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
  const [choosing, setChoosing] = useState(false);
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
            <Header
              joinData={joinData}
              showWardrobePrompt={!result && !choosing}
            />
            {result ? (
              <ResultScreen
                appearance={result.effective_appearance}
                wardrobeChannels={joinData.wardrobe_channels}
                channels={joinData.channels}
              />
            ) : (
              <PickOutfitForm
                code={code}
                joinData={joinData}
                onPicked={setPickedRow}
                onError={showError}
                onChoosingChange={setChoosing}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default PickOutfit;
