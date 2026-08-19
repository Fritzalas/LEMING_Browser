import ROOT
import os
import sys
# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to 
# the sys.path.
sys.path.append(parent)
from Exceptions.cppError import cppError

_cpp_vector_filter_helpers_loaded = False


def load_cpp_vector_filter_helpers() -> None:
    global _cpp_vector_filter_helpers_loaded

    if _cpp_vector_filter_helpers_loaded:
        return

    if hasattr(
        ROOT,
        "SmartRDFCutHelpersLoaded",
    ):
        _cpp_vector_filter_helpers_loaded = True
        return

    declaration_succeeded = (
        ROOT.gInterpreter.Declare(
            r"""
            #include <algorithm>
            #include <cstddef>
            #include <cstring>
            #include <stdexcept>
            #include <string>
            #include <ROOT/RVec.hxx>


            bool SmartRDFCutHelpersLoaded()
            {
                return true;
            }


            namespace SmartRDFCut
            {
                /*
                 * -------------------------------------------------
                 * ONE STRING STORED AS RVec<char>
                 * -------------------------------------------------
                 */

                inline bool CharArrayEquals(
                    const ROOT::VecOps::RVec<char>& values,
                    const char* expected
                )
                {
                    const auto end = std::find(
                        values.begin(),
                        values.end(),
                        '\0'
                    );

                    const std::size_t value_length =
                        static_cast<std::size_t>(
                            std::distance(
                                values.begin(),
                                end
                            )
                        );

                    const std::size_t expected_length =
                        std::strlen(expected);

                    if (
                        value_length
                        != expected_length
                    )
                    {
                        return false;
                    }

                    return std::equal(
                        values.begin(),
                        end,
                        expected
                    );
                }


                /*
                 * -------------------------------------------------
                 * VECTOR OF STRINGS
                 * -------------------------------------------------
                 */

                template <typename StringType>
                ROOT::VecOps::RVec<int> StringVectorEquals(
                    const ROOT::VecOps::RVec<StringType>& values,
                    const std::string& expected
                )
                {
                    ROOT::VecOps::RVec<int> result(
                        values.size()
                    );

                    for (
                        std::size_t i = 0;
                        i < values.size();
                        ++i
                    )
                    {
                        result[i] = (
                            values[i] == expected
                        );
                    }

                    return result;
                }


                template <typename StringType>
                ROOT::VecOps::RVec<int> StringVectorNotEquals(
                    const ROOT::VecOps::RVec<StringType>& values,
                    const std::string& expected
                )
                {
                    ROOT::VecOps::RVec<int> result(
                        values.size()
                    );

                    for (
                        std::size_t i = 0;
                        i < values.size();
                        ++i
                    )
                    {
                        result[i] = (
                            values[i] != expected
                        );
                    }

                    return result;
                }

                inline ROOT::VecOps::RVec<int> BoolVectorToInt(
                    const ROOT::VecOps::RVec<bool>& values
                )
                {
                    ROOT::VecOps::RVec<int> result(values.size());

                    for (
                        std::size_t i = 0;
                        i < values.size();
                        ++i
                    )
                    {
                        result[i] = values[i] ? 1 : 0;
                    }

                    return result;
                }


                /*
                 * -------------------------------------------------
                 * GENERIC VECTOR MASKING
                 * -------------------------------------------------
                 *
                 * Works for:
                 *
                 * RVec<int>
                 * RVec<float>
                 * RVec<double>
                 * RVec<bool>
                 * RVec<std::string>
                 * ...
                 */

                template <typename T, typename M>
                ROOT::VecOps::RVec<T> ApplyMask(
                    const ROOT::VecOps::RVec<T>& values,
                    const ROOT::VecOps::RVec<M>& mask,
                    const char* column_name
                )
                {
                    if (
                        values.size()
                        != mask.size()
                    )
                    {
                        throw std::runtime_error(
                            std::string(
                                "Cannot mask vector column '"
                            )
                            + column_name
                            + "': vector length "
                            + std::to_string(
                                values.size()
                            )
                            + " differs from mask length "
                            + std::to_string(
                                mask.size()
                            )
                            + "."
                        );
                    }

                    return values[mask];
                }
            }
            """
        )
    )

    if not declaration_succeeded:
        raise cppError(
            "ROOT failed to declare the "
            "smart vector-filter C++ helpers."
        )

    if not hasattr(
        ROOT,
        "SmartRDFCutHelpersLoaded",
    ):
        raise cppError(
            "The smart vector-filter marker "
            "was not exposed by ROOT."
        )

    _cpp_vector_filter_helpers_loaded = True