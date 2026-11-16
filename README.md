# open-diag-laptop

A car diagnostic app on an ordinary laptop: plug a USB OBD-II cable into the car, read codes, live data or a test
drive, and work through a diagnosis built on **your car's own service manual**. The answers can come from a model on
the laptop, a bigger model on your desktop, an API key (ChatGPT, Claude, Gemini, Grok), or a subscription you're
already signed into (Claude Code, Gemini CLI/agy, Codex), so no GPU is needed.

This is a side project of [open-diag-cyberdeck](https://github.com/charlie-nolan/open-diag-cyberdeck), the Orange Pi
5 diagnostic deck. All the code lives there; this repo holds:

| | |
|---|---|
| [docs/LAPTOP_GUIDE.md](docs/LAPTOP_GUIDE.md) | Step-by-step guide from nothing to a working laptop setup, written for people who have never used a terminal |
| [setup.sh](setup.sh) | Downloads open-diag-cyberdeck at the version the guide was tested with ([CORE_VERSION](CORE_VERSION)) |
| [config/](config/) | Ready-to-edit settings files for each way of getting answers |
| [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) | What was tested, how it was graded (blind), and what helped |
| [BUILD_ESTIMATES.md](https://github.com/charlie-nolan/open-diag-cyberdeck/blob/main/docs/BUILD_ESTIMATES.md) (in open-diag-cyberdeck) | How long building a car's database takes, and how it scales |
| [tests/sim/](tests/sim/) | The simulation harness, the blind grader, the 40 test cases and their grades |

## Quick start

```bash
cd ~
git clone https://github.com/charlie-nolan/open-diag-laptop.git
bash open-diag-laptop/setup.sh
```

Then follow [the guide](docs/LAPTOP_GUIDE.md) from section 6.

## Read this first

- Tested on two cars only (a 2002 Subaru Forester and a 2003 Chevy Tahoe).
- The AI can be wrong. The app checks the data and cites the manual, but you are the mechanic.
- Service manuals are copyrighted. The database you build is for your own use; don't share it.

## License

GPL-3.0, like open-diag-cyberdeck (see [LICENSE](LICENSE)).
