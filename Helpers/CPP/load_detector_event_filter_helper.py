
import ROOT
import os
import sys


current = os.path.dirname(
    os.path.realpath(__file__)
)

parent = os.path.dirname(current)

if parent not in sys.path:
    sys.path.append(parent)


from Exceptions.cppError import cppError


_HELPER_DECLARED = False


def declare_event_group_helper() -> None:
    """Declare the detector-event grouping helper once."""
    global _HELPER_DECLARED

    if _HELPER_DECLARED:
        return

    code = r"""
    #include <ROOT/RVec.hxx>

    #include <algorithm>
    #include <cstddef>
    #include <cstdint>
    #include <cstring>
    #include <memory>
    #include <mutex>
    #include <stdexcept>
    #include <string>
    #include <type_traits>
    #include <unordered_map>
    #include <utility>
    #include <vector>


    namespace SmartDetectorEventFilter
    {
        // ------------------------------------------------------------------
        // Event key
        // ------------------------------------------------------------------

        struct EventKey
        {
            std::uint64_t run = 0;
            std::uint64_t subrun = 0;
            std::uint64_t event = 0;

            bool operator==(
                const EventKey& other
            ) const noexcept
            {
                return (
                    run == other.run
                    &&
                    subrun == other.subrun
                    &&
                    event == other.event
                );
            }

            bool operator<(
                const EventKey& other
            ) const noexcept
            {
                if (run != other.run)
                    return run < other.run;

                if (subrun != other.subrun)
                    return subrun < other.subrun;

                return event < other.event;
            }
        };


        struct EventKeyHash
        {
            static inline std::uint64_t Mix(
                std::uint64_t value
            ) noexcept
            {
                // SplitMix64 finalizer.
                value ^= value >> 30;
                value *= 0xbf58476d1ce4e5b9ULL;

                value ^= value >> 27;
                value *= 0x94d049bb133111ebULL;

                value ^= value >> 31;

                return value;
            }

            std::size_t operator()(
                const EventKey& key
            ) const noexcept
            {
                const std::uint64_t a = Mix(key.run);
                const std::uint64_t b = Mix(key.subrun);
                const std::uint64_t c = Mix(key.event);

                return static_cast<std::size_t>(
                    a
                    ^ (b + 0x9e3779b97f4a7c15ULL + (a << 6) + (a >> 2))
                    ^ (c + 0x9e3779b97f4a7c15ULL + (b << 6) + (b >> 2))
                );
            }
        };


        // ------------------------------------------------------------------
        // State
        // ------------------------------------------------------------------

        struct GroupState
        {
            std::uint64_t seen = 0;
            std::uint64_t failed = 0;
        };


        struct Context
        {
            std::uint64_t required_mask = 0;

            // One map per RDF processing slot. No locking is needed while
            // Observe() is running.
            std::vector<
                std::unordered_map<
                    EventKey,
                    GroupState,
                    EventKeyHash
                >
            > slot_maps;

            // detector name hash -> detector index
            //
            // We hash the detector string exactly once per row instead of
            // comparing against every requested detector.
            std::unordered_map<
                std::uint64_t,
                unsigned int
            > detector_hash_to_index;

            // Used only to confirm equality after a hash hit.
            std::vector<std::string> detector_names;

            // Immutable after Finalize().
            //
            // A sorted vector is much denser than unordered_set and gives
            // cache-friendly membership checks in the second RDF pass.
            std::vector<EventKey> accepted_events;


            Context(
                std::size_t number_of_slots,
                std::uint64_t required,
                unsigned int detector_count,
                std::size_t estimated_unique_events
            )
                :
                required_mask(required),
                slot_maps(number_of_slots),
                detector_names(detector_count)
            {
                detector_hash_to_index.reserve(
                    static_cast<std::size_t>(detector_count) * 2
                );

                detector_hash_to_index.max_load_factor(0.8f);

                if (estimated_unique_events != 0)
                {
                    // Events are normally distributed over slots.
                    //
                    // Give some extra room because the same event can
                    // occasionally be processed by multiple RDF slots.
                    const std::size_t per_slot =
                        (
                            estimated_unique_events
                            / number_of_slots
                        )
                        + 1024;

                    for (auto& map : slot_maps)
                    {
                        map.reserve(per_slot);
                        map.max_load_factor(0.8f);
                    }
                }
                else
                {
                    for (auto& map : slot_maps)
                    {
                        map.max_load_factor(0.8f);
                    }
                }
            }
        };


        // ------------------------------------------------------------------
        // Registry
        //
        // Only setup/finalization touches this.
        // Observe() and Accepted() receive Context* directly.
        // ------------------------------------------------------------------

        inline std::mutex registry_mutex;

        inline std::unordered_map<
            std::uint64_t,
            std::unique_ptr<Context>
        > contexts;


        inline std::uint64_t RequiredMask(
            unsigned int detector_count
        )
        {
            if (
                detector_count == 0
                ||
                detector_count > 64
            )
            {
                throw std::runtime_error(
                    "detector_count must be in [1, 64]"
                );
            }

            if (detector_count == 64)
                return ~std::uint64_t{0};

            return (
                std::uint64_t{1}
                << detector_count
            ) - std::uint64_t{1};
        }


        inline Context* CreateContext(
            std::uint64_t context_id,
            std::size_t number_of_slots,
            unsigned int detector_count,
            std::size_t estimated_unique_events = 0
        )
        {
            if (number_of_slots == 0)
            {
                throw std::runtime_error(
                    "number_of_slots must be > 0"
                );
            }

            auto context =
                std::make_unique<Context>(
                    number_of_slots,
                    RequiredMask(detector_count),
                    detector_count,
                    estimated_unique_events
                );

            Context* raw = context.get();

            {
                std::lock_guard<std::mutex>
                    lock(registry_mutex);

                contexts[context_id] =
                    std::move(context);
            }

            return raw;
        }


        inline Context* GetContext(
            std::uint64_t context_id
        )
        {
            std::lock_guard<std::mutex>
                lock(registry_mutex);

            const auto iterator =
                contexts.find(context_id);

            if (iterator == contexts.end())
                return nullptr;

            return iterator->second.get();
        }


        inline void DestroyContext(
            std::uint64_t context_id
        )
        {
            std::lock_guard<std::mutex>
                lock(registry_mutex);

            contexts.erase(context_id);
        }


        // ------------------------------------------------------------------
        // Detector hashing
        //
        // FNV-1a is inexpensive for the short detector names normally found
        // here. Most importantly, the detector string is scanned once per
        // row instead of once per requested detector.
        // ------------------------------------------------------------------

        inline constexpr std::uint64_t FNV_OFFSET =
            14695981039346656037ULL;

        inline constexpr std::uint64_t FNV_PRIME =
            1099511628211ULL;


        inline std::uint64_t HashDetectorBytes(
            const unsigned char* data,
            std::size_t size
        ) noexcept
        {
            std::uint64_t hash = FNV_OFFSET;

            for (std::size_t i = 0; i < size; ++i)
            {
                hash ^= static_cast<std::uint64_t>(data[i]);
                hash *= FNV_PRIME;
            }

            return hash;
        }


        inline std::uint64_t HashDetector(
            const std::string& value
        ) noexcept
        {
            return HashDetectorBytes(
                reinterpret_cast<const unsigned char*>(
                    value.data()
                ),
                value.size()
            );
        }


        inline std::uint64_t HashDetector(
            const char* value
        ) noexcept
        {
            if (value == nullptr)
                return 0;

            std::uint64_t hash = FNV_OFFSET;

            while (*value != '\0')
            {
                hash ^=
                    static_cast<unsigned char>(*value);

                hash *= FNV_PRIME;

                ++value;
            }

            return hash;
        }


        template <typename T>
        inline std::uint64_t HashDetector(
            const ROOT::VecOps::RVec<T>& value
        ) noexcept
        {
            using ValueT =
                std::remove_cv_t<T>;

            constexpr bool is_char_type =
                std::is_same_v<ValueT, char>
                ||
                std::is_same_v<ValueT, signed char>
                ||
                std::is_same_v<ValueT, unsigned char>;

            if constexpr (!is_char_type)
            {
                return 0;
            }
            else
            {
                std::uint64_t hash = FNV_OFFSET;

                for (std::size_t i = 0; i < value.size(); ++i)
                {
                    const auto byte =
                        static_cast<unsigned char>(
                            value[i]
                        );

                    if (byte == 0)
                        break;

                    hash ^= byte;
                    hash *= FNV_PRIME;
                }

                return hash;
            }
        }


        // ------------------------------------------------------------------
        // Exact equality
        //
        // Called only after a detector hash matches.
        // ------------------------------------------------------------------

        inline bool DetectorEquals(
            const std::string& value,
            const std::string& expected
        ) noexcept
        {
            return value == expected;
        }


        inline bool DetectorEquals(
            const char* value,
            const std::string& expected
        ) noexcept
        {
            if (value == nullptr)
                return false;

            return expected == value;
        }


        template <typename T>
        inline bool DetectorEquals(
            const ROOT::VecOps::RVec<T>& value,
            const std::string& expected
        ) noexcept
        {
            using ValueT =
                std::remove_cv_t<T>;

            constexpr bool is_char_type =
                std::is_same_v<ValueT, char>
                ||
                std::is_same_v<ValueT, signed char>
                ||
                std::is_same_v<ValueT, unsigned char>;

            if constexpr (!is_char_type)
            {
                return false;
            }
            else
            {
                std::size_t index = 0;

                while (
                    index < value.size()
                    &&
                    value[index] != 0
                    &&
                    index < expected.size()
                )
                {
                    if (
                        static_cast<unsigned char>(
                            value[index]
                        )
                        !=
                        static_cast<unsigned char>(
                            expected[index]
                        )
                    )
                    {
                        return false;
                    }

                    ++index;
                }

                const bool actual_finished =
                    (
                        index >= value.size()
                        ||
                        value[index] == 0
                    );

                const bool expected_finished =
                    index == expected.size();

                return (
                    actual_finished
                    &&
                    expected_finished
                );
            }
        }


        inline void AddDetector(
            Context* context,
            unsigned int detector_index,
            const char* detector_name
        )
        {
            if (context == nullptr)
            {
                throw std::runtime_error(
                    "null detector filter context"
                );
            }

            if (
                detector_index
                >= context->detector_names.size()
            )
            {
                throw std::runtime_error(
                    "detector index out of range"
                );
            }

            if (detector_name == nullptr)
            {
                throw std::runtime_error(
                    "detector name cannot be null"
                );
            }

            std::string name(detector_name);

            const std::uint64_t hash =
                HashDetector(name);

            const auto [iterator, inserted] =
                context->detector_hash_to_index.emplace(
                    hash,
                    detector_index
                );

            if (!inserted)
            {
                const unsigned int previous_index =
                    iterator->second;

                // Same name is already rejected in Python. Therefore a
                // duplicate hash here means two distinct requested detector
                // names collided.
                if (
                    previous_index
                        >= context->detector_names.size()
                    ||
                    context->detector_names[
                        previous_index
                    ] != name
                )
                {
                    throw std::runtime_error(
                        "detector-name hash collision"
                    );
                }
            }

            context->detector_names[
                detector_index
            ] = std::move(name);
        }


        template <typename DetectorT>
        inline int DetectorIndex(
            const Context* context,
            const DetectorT& detector
        ) noexcept
        {
            if (context == nullptr)
                return -1;

            const std::uint64_t hash =
                HashDetector(detector);

            const auto iterator =
                context
                    ->detector_hash_to_index
                    .find(hash);

            if (
                iterator
                ==
                context->detector_hash_to_index.end()
            )
            {
                return -1;
            }

            const unsigned int index =
                iterator->second;

            if (
                index
                >= context->detector_names.size()
            )
            {
                return -1;
            }

            // Protect against collisions with detector names that were not
            // part of the requested detector set.
            if (
                !DetectorEquals(
                    detector,
                    context->detector_names[index]
                )
            )
            {
                return -1;
            }

            return static_cast<int>(index);
        }


        // ------------------------------------------------------------------
        // Generic value conversion
        // ------------------------------------------------------------------

        template <typename T>
        inline std::uint64_t ToUInt64(
            const T& value
        ) noexcept
        {
            return static_cast<std::uint64_t>(
                value
            );
        }


        template <
            typename RunT,
            typename SubrunT,
            typename EventT
        >
        inline EventKey MakeKey(
            const RunT& run,
            const SubrunT& subrun,
            const EventT& event
        ) noexcept
        {
            return EventKey{
                ToUInt64(run),
                ToUInt64(subrun),
                ToUInt64(event),
            };
        }


        // ------------------------------------------------------------------
        // Cut result conversion
        // ------------------------------------------------------------------

        template <typename T>
        inline bool CutPass(
            const T& value
        )
        {
            return static_cast<bool>(
                value
            );
        }


        template <typename T>
        inline bool CutPass(
            const ROOT::VecOps::RVec<T>& value
        )
        {
            return ROOT::VecOps::All(
                value
            );
        }


        // ------------------------------------------------------------------
        // Hot path
        // ------------------------------------------------------------------

        template <
            typename RunT,
            typename SubrunT,
            typename EventT
        >
        inline unsigned long long Observe(
            Context* context,
            unsigned int slot,
            const RunT& run,
            const SubrunT& subrun,
            const EventT& event,
            int detector_index,
            bool detector_pass
        )
        {
            if (
                context == nullptr
                ||
                detector_index < 0
                ||
                detector_index >= 64
                ||
                static_cast<std::size_t>(slot)
                    >= context->slot_maps.size()
            )
            {
                return 1ULL;
            }

            const EventKey key =
                MakeKey(
                    run,
                    subrun,
                    event
                );

            auto& map =
                context->slot_maps[
                    static_cast<std::size_t>(slot)
                ];

            // try_emplace avoids constructing/defaulting mapped state when
            // the event already exists.
            auto result =
                map.try_emplace(key);

            GroupState& state =
                result.first->second;

            const std::uint64_t bit =
                std::uint64_t{1}
                <<
                static_cast<unsigned int>(
                    detector_index
                );

            state.seen |= bit;

            if (!detector_pass)
                state.failed |= bit;

            return 1ULL;
        }


        // ------------------------------------------------------------------
        // Finalize
        // ------------------------------------------------------------------

        inline void Finalize(
            Context* context
        )
        {
            if (context == nullptr)
                return;

            if (context->slot_maps.empty())
            {
                context->accepted_events.clear();
                return;
            }

            std::size_t approximate_size = 0;

            for (
                const auto& slot_map
                :
                context->slot_maps
            )
            {
                approximate_size +=
                    slot_map.size();
            }

            // Reuse slot 0 as the merge destination.
            //
            // This avoids constructing an additional full-size
            // unordered_map containing every event.
            auto merged =
                std::move(
                    context->slot_maps[0]
                );

            merged.reserve(
                approximate_size
            );

            merged.max_load_factor(0.8f);

            for (
                std::size_t slot = 1;
                slot < context->slot_maps.size();
                ++slot
            )
            {
                auto& source =
                    context->slot_maps[slot];

                for (
                    const auto& item
                    :
                    source
                )
                {
                    auto result =
                        merged.try_emplace(
                            item.first
                        );

                    GroupState& destination =
                        result.first->second;

                    destination.seen |=
                        item.second.seen;

                    destination.failed |=
                        item.second.failed;
                }

                // Release source-map memory as soon as this slot has been
                // merged.
                std::unordered_map<
                    EventKey,
                    GroupState,
                    EventKeyHash
                >().swap(source);
            }

            context->accepted_events.clear();

            // Worst case: every event is accepted.
            context->accepted_events.reserve(
                merged.size()
            );

            const std::uint64_t required =
                context->required_mask;

            for (
                const auto& item
                :
                merged
            )
            {
                const GroupState& state =
                    item.second;

                const bool all_seen =
                    (
                        (
                            state.seen
                            &
                            required
                        )
                        ==
                        required
                    );

                const bool none_failed =
                    (
                        (
                            state.failed
                            &
                            required
                        )
                        ==
                        0
                    );

                if (
                    all_seen
                    &&
                    none_failed
                )
                {
                    context
                        ->accepted_events
                        .push_back(item.first);
                }
            }

            // Release the giant mutable hash map before the second pass.
            decltype(merged)().swap(
                merged
            );

            context->slot_maps.clear();
            context->slot_maps.shrink_to_fit();

            // Compact immutable representation for the second pass.
            std::sort(
                context->accepted_events.begin(),
                context->accepted_events.end()
            );

            context->accepted_events.shrink_to_fit();
        }


        // ------------------------------------------------------------------
        // Second pass
        // ------------------------------------------------------------------

        template <
            typename RunT,
            typename SubrunT,
            typename EventT
        >
        inline bool Accepted(
            const Context* context,
            const RunT& run,
            const SubrunT& subrun,
            const EventT& event
        ) noexcept
        {
            if (context == nullptr)
                return false;

            const EventKey key =
                MakeKey(
                    run,
                    subrun,
                    event
                );

            return std::binary_search(
                context->accepted_events.begin(),
                context->accepted_events.end(),
                key
            );
        }


        inline std::size_t AcceptedCount(
            const Context* context
        ) noexcept
        {
            return (
                context == nullptr
                ? 0
                : context->accepted_events.size()
            );
        }
    }
    """

    success = ROOT.gInterpreter.Declare(code)

    if not success:
        raise cppError(
            "Could not compile the generic "
            "detector-event filter helper."
        )

    _HELPER_DECLARED = True