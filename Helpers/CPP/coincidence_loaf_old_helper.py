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


_COINCIDENCE_OLD_HELPER_DECLARED = False


def declare_coincidence_loaf_old_helper() -> None:
    global _COINCIDENCE_OLD_HELPER_DECLARED

    if _COINCIDENCE_OLD_HELPER_DECLARED:
        return

    code = r"""
    #include <ROOT/RVec.hxx>

    #include <algorithm>
    #include <cstddef>
    #include <cstdint>
    #include <limits>
    #include <memory>
    #include <mutex>
    #include <stdexcept>
    #include <string>
    #include <type_traits>
    #include <unordered_map>
    #include <utility>
    #include <vector>


    namespace CoincidenceLoafOld
    {
        // ==============================================================
        // Event key
        // ==============================================================

        struct EventKey
        {
            std::uint64_t run;
            std::uint64_t subrun;
            std::uint64_t event;

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
        };


        struct EventKeyHash
        {
            static inline std::uint64_t Mix(
                std::uint64_t value
            ) noexcept
            {
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
                const std::uint64_t a =
                    Mix(key.run);

                const std::uint64_t b =
                    Mix(key.subrun);

                const std::uint64_t c =
                    Mix(key.event);

                std::uint64_t hash = a;

                hash ^= (
                    b
                    +
                    0x9e3779b97f4a7c15ULL
                    +
                    (hash << 6)
                    +
                    (hash >> 2)
                );

                hash ^= (
                    c
                    +
                    0x9e3779b97f4a7c15ULL
                    +
                    (hash << 6)
                    +
                    (hash >> 2)
                );

                return static_cast<std::size_t>(
                    hash
                );
            }
        };


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
                static_cast<std::uint64_t>(
                    run
                ),
                static_cast<std::uint64_t>(
                    subrun
                ),
                static_cast<std::uint64_t>(
                    event
                )
            };
        }


        // ==============================================================
        // Detector hashing
        // ==============================================================

        inline constexpr std::uint64_t FNV_OFFSET =
            14695981039346656037ULL;

        inline constexpr std::uint64_t FNV_PRIME =
            1099511628211ULL;


        inline std::uint64_t HashDetectorBytes(
            const unsigned char* data,
            std::size_t size
        ) noexcept
        {
            std::uint64_t hash =
                FNV_OFFSET;

            for (
                std::size_t index = 0;
                index < size;
                ++index
            )
            {
                hash ^=
                    static_cast<std::uint64_t>(
                        data[index]
                    );

                hash *=
                    FNV_PRIME;
            }

            return hash;
        }


        inline std::uint64_t HashDetector(
            const std::string& value
        ) noexcept
        {
            return HashDetectorBytes(
                reinterpret_cast<
                    const unsigned char*
                >(
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
            {
                return 0;
            }

            std::uint64_t hash =
                FNV_OFFSET;

            while (*value != '\0')
            {
                hash ^=
                    static_cast<unsigned char>(
                        *value
                    );

                hash *=
                    FNV_PRIME;

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
                std::uint64_t hash =
                    FNV_OFFSET;

                for (
                    std::size_t index = 0;
                    index < value.size();
                    ++index
                )
                {
                    const auto byte =
                        static_cast<unsigned char>(
                            value[index]
                        );

                    if (byte == 0)
                    {
                        break;
                    }

                    hash ^= byte;
                    hash *= FNV_PRIME;
                }

                return hash;
            }
        }


        // ==============================================================
        // Detector equality
        // ==============================================================

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
            return (
                value != nullptr
                &&
                expected == value
            );
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
                    (
                        index
                        ==
                        expected.size()
                    );

                return (
                    actual_finished
                    &&
                    expected_finished
                );
            }
        }


        // ==============================================================
        // Per-event state
        // ==============================================================

        struct GroupState
        {
            // Bit mask indicating which requested detectors occurred.
            std::uint64_t seen = 0;

            // Only detector 0 and detector 1 contribute to time_coinc.
            bool has_time_0 = false;
            bool has_time_1 = false;

            double time_0 = 0.0;
            double time_1 = 0.0;

            // Smallest rdfentry_ wins when detector 0/1 occurs
            // multiple times.
            std::uint64_t entry_0 =
                std::numeric_limits<
                    std::uint64_t
                >::max();

            std::uint64_t entry_1 =
                std::numeric_limits<
                    std::uint64_t
                >::max();
        };


        // ==============================================================
        // Context
        // ==============================================================

        using EventMap =
            std::unordered_map<
                EventKey,
                GroupState,
                EventKeyHash
            >;

        using ResultMap =
            std::unordered_map<
                std::uint64_t,
                double
            >;


        struct Context
        {
            std::uint64_t required_mask = 0;

            // Each RDF slot writes only to its own map.
            //
            // Therefore the hot first pass requires no mutex.
            std::vector<EventMap>
                slot_maps;

            // detector hash -> detector index
            std::unordered_map<
                std::uint64_t,
                unsigned int
            >
                detector_hash_to_index;

            // Retained to verify hash collisions.
            std::vector<std::string>
                detector_names;

            // Optimized second-pass table:
            //
            //     selected rdfentry_ -> time_coinc
            //
            // Rows which should receive NaN simply do not appear.
            ResultMap
                results;


            Context(
                std::size_t number_of_slots,
                unsigned int detector_count
            )
                :
                required_mask(
                    detector_count == 64
                    ?
                    ~std::uint64_t{0}
                    :
                    (
                        std::uint64_t{1}
                        << detector_count
                    )
                    -
                    std::uint64_t{1}
                ),
                slot_maps(
                    number_of_slots
                ),
                detector_names(
                    detector_count
                )
            {
                detector_hash_to_index.reserve(
                    static_cast<std::size_t>(
                        detector_count
                    )
                    *
                    2
                );

                detector_hash_to_index
                    .max_load_factor(
                        0.8f
                    );
            }
        };


        // ==============================================================
        // Context registry
        // ==============================================================

        inline std::mutex
            registry_mutex;

        inline std::unordered_map<
            std::uint64_t,
            std::unique_ptr<Context>
        >
            contexts;


        inline Context* CreateContext(
            std::uint64_t context_id,
            std::size_t number_of_slots,
            unsigned int detector_count
        )
        {
            if (number_of_slots == 0)
            {
                throw std::runtime_error(
                    "number_of_slots must be > 0"
                );
            }

            if (
                detector_count < 2
                ||
                detector_count > 64
            )
            {
                throw std::runtime_error(
                    "detector_count must be in [2, 64]"
                );
            }

            auto context =
                std::make_unique<Context>(
                    number_of_slots,
                    detector_count
                );

            Context* raw =
                context.get();

            {
                std::lock_guard<std::mutex>
                    lock(
                        registry_mutex
                    );

                contexts[
                    context_id
                ] =
                    std::move(
                        context
                    );
            }

            return raw;
        }


        inline Context* GetContext(
            std::uint64_t context_id
        )
        {
            std::lock_guard<std::mutex>
                lock(
                    registry_mutex
                );

            const auto iterator =
                contexts.find(
                    context_id
                );

            if (
                iterator
                ==
                contexts.end()
            )
            {
                return nullptr;
            }

            return iterator->second.get();
        }


        inline void DestroyContext(
            std::uint64_t context_id
        )
        {
            std::lock_guard<std::mutex>
                lock(
                    registry_mutex
                );

            contexts.erase(
                context_id
            );
        }


        // ==============================================================
        // Detector registration
        // ==============================================================

        inline void AddDetector(
            Context* context,
            unsigned int detector_index,
            const char* detector_name
        )
        {
            if (context == nullptr)
            {
                throw std::runtime_error(
                    "null coincidence context"
                );
            }

            if (
                detector_index
                >=
                context
                    ->detector_names
                    .size()
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

            std::string name(
                detector_name
            );

            const std::uint64_t hash =
                HashDetector(
                    name
                );

            const auto [
                iterator,
                inserted
            ] =
                context
                    ->detector_hash_to_index
                    .emplace(
                        hash,
                        detector_index
                    );

            if (!inserted)
            {
                const unsigned int
                    previous_index =
                        iterator->second;

                if (
                    previous_index
                    >=
                    context
                        ->detector_names
                        .size()
                    ||
                    context
                        ->detector_names[
                            previous_index
                        ]
                    !=
                    name
                )
                {
                    throw std::runtime_error(
                        "detector-name hash collision"
                    );
                }
            }

            context
                ->detector_names[
                    detector_index
                ] =
                    std::move(
                        name
                    );
        }


        // ==============================================================
        // Detector lookup
        // ==============================================================

        template <typename DetectorT>
        inline int DetectorIndex(
            const Context* context,
            const DetectorT& detector
        ) noexcept
        {
            if (context == nullptr)
            {
                return -1;
            }

            const std::uint64_t hash =
                HashDetector(
                    detector
                );

            const auto iterator =
                context
                    ->detector_hash_to_index
                    .find(
                        hash
                    );

            if (
                iterator
                ==
                context
                    ->detector_hash_to_index
                    .end()
            )
            {
                return -1;
            }

            const unsigned int index =
                iterator->second;

            if (
                index
                >=
                context
                    ->detector_names
                    .size()
            )
            {
                return -1;
            }

            if (
                !DetectorEquals(
                    detector,
                    context
                        ->detector_names[
                            index
                        ]
                )
            )
            {
                return -1;
            }

            return static_cast<int>(
                index
            );
        }


        // ==============================================================
        // First-pass event update
        // ==============================================================

        template <
            typename RunT,
            typename SubrunT,
            typename EventT,
            typename TimeT
        >
        inline void ObserveIndexed(
            Context* context,
            unsigned int slot,
            const RunT& run,
            const SubrunT& subrun,
            const EventT& event,
            unsigned int detector_index,
            const TimeT& time,
            std::uint64_t entry
        ) noexcept
        {
            const EventKey key =
                MakeKey(
                    run,
                    subrun,
                    event
                );

            auto& map =
                context
                    ->slot_maps[
                        static_cast<std::size_t>(
                            slot
                        )
                    ];

            auto [
                iterator,
                inserted
            ] =
                map.try_emplace(
                    key
                );

            (void)inserted;

            GroupState& state =
                iterator->second;

            state.seen |= (
                std::uint64_t{1}
                <<
                detector_index
            );

            // ----------------------------------------------------------
            // First requested detector
            // ----------------------------------------------------------

            if (detector_index == 0)
            {
                if (
                    !state.has_time_0
                    ||
                    entry < state.entry_0
                )
                {
                    state.has_time_0 =
                        true;

                    state.time_0 =
                        static_cast<double>(
                            time
                        );

                    state.entry_0 =
                        entry;
                }

                return;
            }

            // ----------------------------------------------------------
            // Second requested detector
            // ----------------------------------------------------------

            if (detector_index == 1)
            {
                if (
                    !state.has_time_1
                    ||
                    entry < state.entry_1
                )
                {
                    state.has_time_1 =
                        true;

                    state.time_1 =
                        static_cast<double>(
                            time
                        );

                    state.entry_1 =
                        entry;
                }
            }
        }


        // ==============================================================
        // Combined RDF first-pass operation
        //
        // This replaces:
        //
        //     DetectorIndex Define
        //          +
        //     Observe Define
        //          +
        //     Sum
        //
        // with one Filter predicate.
        // ==============================================================

        template <
            typename DetectorT,
            typename RunT,
            typename SubrunT,
            typename EventT,
            typename TimeT
        >
        inline bool ObserveRow(
            Context* context,
            unsigned int slot,
            const DetectorT& detector,
            const RunT& run,
            const SubrunT& subrun,
            const EventT& event,
            const TimeT& time,
            std::uint64_t entry
        ) noexcept
        {
            if (
                context == nullptr
                ||
                static_cast<std::size_t>(
                    slot
                )
                >=
                context
                    ->slot_maps
                    .size()
            )
            {
                return false;
            }

            const int index =
                DetectorIndex(
                    context,
                    detector
                );

            // Reject unrelated detector rows immediately.
            if (index < 0)
            {
                return false;
            }

            ObserveIndexed(
                context,
                slot,
                run,
                subrun,
                event,
                static_cast<unsigned int>(
                    index
                ),
                time,
                entry
            );

            return true;
        }


        // ==============================================================
        // Merge state
        // ==============================================================

        inline void MergeState(
            GroupState& destination,
            const GroupState& source
        ) noexcept
        {
            destination.seen |=
                source.seen;

            if (
                source.has_time_0
                &&
                (
                    !destination.has_time_0
                    ||
                    source.entry_0
                    <
                    destination.entry_0
                )
            )
            {
                destination.has_time_0 =
                    true;

                destination.time_0 =
                    source.time_0;

                destination.entry_0 =
                    source.entry_0;
            }

            if (
                source.has_time_1
                &&
                (
                    !destination.has_time_1
                    ||
                    source.entry_1
                    <
                    destination.entry_1
                )
            )
            {
                destination.has_time_1 =
                    true;

                destination.time_1 =
                    source.time_1;

                destination.entry_1 =
                    source.entry_1;
            }
        }


        // ==============================================================
        // Finalize
        // ==============================================================

        inline void Finalize(
            Context* context
        )
        {
            if (
                context == nullptr
                ||
                context
                    ->slot_maps
                    .empty()
            )
            {
                return;
            }

            // ----------------------------------------------------------
            // Start with the largest slot map.
            //
            // This minimizes the number of nodes that need to be inserted
            // into the merged hash table.
            // ----------------------------------------------------------

            std::size_t largest_slot =
                0;

            std::size_t approximate_size =
                context
                    ->slot_maps[0]
                    .size();

            for (
                std::size_t slot = 1;
                slot <
                    context
                        ->slot_maps
                        .size();
                ++slot
            )
            {
                const std::size_t size =
                    context
                        ->slot_maps[
                            slot
                        ]
                        .size();

                approximate_size +=
                    size;

                if (
                    size
                    >
                    context
                        ->slot_maps[
                            largest_slot
                        ]
                        .size()
                )
                {
                    largest_slot =
                        slot;
                }
            }

            EventMap merged =
                std::move(
                    context
                        ->slot_maps[
                            largest_slot
                        ]
                );

            merged.max_load_factor(
                0.8f
            );

            // Upper-bound reservation prevents repeated rehashing.
            if (
                approximate_size
                >
                merged.size()
            )
            {
                merged.reserve(
                    approximate_size
                );
            }

            // ----------------------------------------------------------
            // Merge remaining slot maps
            // ----------------------------------------------------------

            for (
                std::size_t slot = 0;
                slot <
                    context
                        ->slot_maps
                        .size();
                ++slot
            )
            {
                if (slot == largest_slot)
                {
                    continue;
                }

                auto& source =
                    context
                        ->slot_maps[
                            slot
                        ];

                for (
                    const auto& item :
                    source
                )
                {
                    auto [
                        iterator,
                        inserted
                    ] =
                        merged.try_emplace(
                            item.first,
                            item.second
                        );

                    if (!inserted)
                    {
                        MergeState(
                            iterator->second,
                            item.second
                        );
                    }
                }

                EventMap{}.swap(
                    source
                );
            }

            // ----------------------------------------------------------
            // Build optimized second-pass table
            //
            // Instead of:
            //
            //     EventKey -> {time, output_entry}
            //
            // store only:
            //
            //     output_entry -> time
            //
            // because all other rows must return NaN anyway.
            // ----------------------------------------------------------

            context
                ->results
                .clear();

            context
                ->results
                .max_load_factor(
                    0.8f
                );

            // At most one result can exist per merged event.
            context
                ->results
                .reserve(
                    merged.size()
                );

            const std::uint64_t required =
                context
                    ->required_mask;

            for (
                const auto& item :
                merged
            )
            {
                const GroupState& state =
                    item.second;

                if (
                    (
                        state.seen
                        &
                        required
                    )
                    !=
                    required
                )
                {
                    continue;
                }

                if (
                    !state.has_time_0
                    ||
                    !state.has_time_1
                )
                {
                    continue;
                }

                context
                    ->results
                    .emplace(
                        state.entry_0,
                        (
                            state.time_0
                            +
                            state.time_1
                        )
                        *
                        0.5
                    );
            }

            // Release first-pass event maps.
            EventMap{}.swap(
                merged
            );

            context
                ->slot_maps
                .clear();

            // Intentionally no shrink_to_fit().
        }


        // ==============================================================
        // Second pass
        // ==============================================================

        inline double CoincidenceTime(
            const Context* context,
            std::uint64_t entry
        ) noexcept
        {
            if (context == nullptr)
            {
                return
                    std::numeric_limits<double>
                        ::quiet_NaN();
            }

            const auto iterator =
                context
                    ->results
                    .find(
                        entry
                    );

            if (
                iterator
                ==
                context
                    ->results
                    .end()
            )
            {
                return
                    std::numeric_limits<double>
                        ::quiet_NaN();
            }

            return iterator->second;
        }


        inline std::size_t ResultCount(
            const Context* context
        ) noexcept
        {
            if (context == nullptr)
            {
                return 0;
            }

            return
                context
                    ->results
                    .size();
        }
    }
    """

    success = ROOT.gInterpreter.Declare(
        code
    )

    if not success:
        raise cppError(
            "Could not compile "
            "coincidence_loaf_old helper."
        )

    _COINCIDENCE_OLD_HELPER_DECLARED = True