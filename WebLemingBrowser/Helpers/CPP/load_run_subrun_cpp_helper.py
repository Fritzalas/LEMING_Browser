import ROOT

def load_run_subrun_cpp_helpers() -> None:
    run_helpers_loaded = all(
        hasattr(ROOT, helper_name)
        for helper_name in (
            "ExtractRunAndSubrunFromSample",
            "ExtractRunNumberFromSample",
            "ExtractSubrunNumberFromSample",
        )
    )

    if run_helpers_loaded:
        print("Run/subrun C++ helpers are already loaded.")
        return

    print("Loading run/subrun C++ helpers.")

    ROOT.gInterpreter.Declare(
        r"""
        #include <regex>
        #include <stdexcept>
        #include <string>
        #include <utility>

        std::pair<unsigned int, unsigned int>
        ExtractRunAndSubrunFromSample(
            const std::string& sample_name
        )
        {
            static const std::regex filename_pattern(
                R"(run([0-9]+)_([0-9]+)\.mid\.root)"
            );

            std::smatch match;

            if (!std::regex_search(
                    sample_name,
                    match,
                    filename_pattern
                ))
            {
                throw std::runtime_error(
                    "Could not extract run and subrun numbers "
                    "from ROOT sample: "
                    + sample_name
                );
            }

            const auto run_number =
                static_cast<unsigned int>(
                    std::stoul(match[1].str())
                );

            const auto subrun_number =
                static_cast<unsigned int>(
                    std::stoul(match[2].str())
                );

            return {
                run_number,
                subrun_number,
            };
        }

        unsigned int ExtractRunNumberFromSample(
            const std::string& sample_name
        )
        {
            return ExtractRunAndSubrunFromSample(
                sample_name
            ).first;
        }

        unsigned int ExtractSubrunNumberFromSample(
            const std::string& sample_name
        )
        {
            return ExtractRunAndSubrunFromSample(
                sample_name
            ).second;
        }
        """
    )

    print("Run/subrun C++ helpers loaded.")