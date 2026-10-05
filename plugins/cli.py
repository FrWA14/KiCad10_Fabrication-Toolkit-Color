# Modified 2026 by Fabrication Toolkit Color: JLCPCB multi-colour silkscreen support (see NOTICE).
import argparse as ap
import os
import sys

from .options import *


def _no_pcbnew_exit(args, error):
    '''Without pcbnew nothing can be plotted: still leave a machine-readable report.'''
    from .color_silkscreen.errors import ColorSilkError
    from .color_silkscreen.report import Report
    report = Report(input_board=args.path)
    report.error(ColorSilkError("E_NO_PCBNEW", "Module pcbnew indisponible : {}".format(error)))
    if args.report:
        report.write(args.report)
    print(report.data["errors"][0], file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    parser = ap.ArgumentParser(prog="Fabrication Toolkit",
                            description="Generates JLCPCB production files from a KiCAD board file")

    parser.add_argument("--path",               "-p",  type=str, help="Path to KiCAD board file", required=True)
    parser.add_argument("--additionalLayers",   "-aL", type=str, help="Additional layers(comma-separated)", metavar="LAYERS")
    parser.add_argument("--user1VCut",          "-u1", action="store_true", help="Set User.1 as V-Cut layer")
    parser.add_argument("--user2AltVCut",       "-u2", action="store_true", help="Set User.2 as alternative Edge-Cut layer")
    parser.add_argument("--autoTranslate",      "-t",  action="store_true", help="Apply automatic position/rotation translations")
    parser.add_argument("--autoFill",           "-f",  action="store_true", help="Apply automatic fill for all zones")
    parser.add_argument("--excludeDNP",         "-e",  action="store_true", help="Exclude DNP components from BOM")
    parser.add_argument("--allActiveLayers",    "-aaL",action="store_true", help="Export all active layers instead of only commonly used ones")
    parser.add_argument("--archiveName",        "-aN", type=str, help="Name of the generated archives", metavar="NAME")
    parser.add_argument("--openBrowser",        "-b",  action="store_true", help="Open webbrowser with directory file overview after generation")
    parser.add_argument("--nonInteractive",     "-nI" ,action="store_true", help="Run in non-Interactive mode. Useful in CI/CD environment.")
    parser.add_argument("--noBackup",           "-nB", action="store_true", help="Do not create backup files")
    parser.add_argument("--topColorImage",      type=str, help="PNG/JPG printed in colour on the top face", metavar="IMAGE")
    parser.add_argument("--bottomColorImage",   type=str, help="PNG/JPG printed in colour on the bottom face (as seen from below)", metavar="IMAGE")
    parser.add_argument("--colorFit",           choices=["stretch", "contain"], default="stretch", help="How the image fills the board outline")
    parser.add_argument("--colorProfile",       choices=["default", "transjlc"], default="default", help="'transjlc' reproduces TransJLC 0.4.0 output")
    parser.add_argument("--report",             type=str, help="Write the colour silkscreen report (JSON) here", metavar="PATH")
    parser.add_argument("--log",                type=str, help="Colour silkscreen log file", metavar="PATH")
    parser.add_argument("--placement",          type=str, help="Placement JSON from the editor (color_placement.json): position/size per face", metavar="FILE")
    parser.add_argument("--debugSvg",           type=str, help="Also write the plaintext colour SVGs to this folder", metavar="DIR")
    args = parser.parse_args()

    try:
        import pcbnew  # type: ignore  # noqa: F401
    except ImportError as e:
        _no_pcbnew_exit(args, e)

    from .thread import ProcessThread

    options = dict()
    options[AUTO_TRANSLATE_OPT] = args.autoTranslate
    options[AUTO_FILL_OPT] = args.autoFill
    options[EXCLUDE_DNP_OPT] = args.excludeDNP
    options[EXTEND_EDGE_CUT_OPT] = args.user1VCut
    options[ALTERNATIVE_EDGE_CUT_OPT] = args.user2AltVCut
    options[ALL_ACTIVE_LAYERS_OPT] = args.allActiveLayers
    options[ARCHIVE_NAME] = args.archiveName
    options[EXTRA_LAYERS] = args.additionalLayers
    options[BACKUP_OPT] = not args.noBackup
    options[TOP_IMAGE_OPT] = os.path.abspath(args.topColorImage) if args.topColorImage else None
    options[BOTTOM_IMAGE_OPT] = os.path.abspath(args.bottomColorImage) if args.bottomColorImage else None
    options[COLOR_FIT_OPT] = args.colorFit
    options[COLOR_PROFILE_OPT] = args.colorProfile
    options[COLOR_REPORT_OPT] = os.path.abspath(args.report) if args.report else None
    options[COLOR_LOG_OPT] = os.path.abspath(args.log) if args.log else None
    options[COLOR_DEBUG_SVG_OPT] = os.path.abspath(args.debugSvg) if args.debugSvg else None
    if args.placement:
        from .color_silkscreen.placement import load_placements
        placements = load_placements(args.placement)
        options[TOP_PLACEMENT_OPT] = placements["top"]
        options[BOTTOM_PLACEMENT_OPT] = placements["bottom"]

    openBrowser = args.openBrowser
    nonInteractive = args.nonInteractive


    path = os.path.abspath(args.path)

    thread = ProcessThread(wx=None, cli=path, options=options, openBrowser=openBrowser, nonInteractive=nonInteractive)
    if thread.is_alive() or thread.ident is not None:
        thread.join()
    if thread.error:
        if thread.ident is None and args.report:  # board never loaded: no report written yet
            from .color_silkscreen.errors import ColorSilkError
            from .color_silkscreen.report import Report
            report = Report(input_board=path)
            report.error(ColorSilkError("E_INTERNAL", "Chargement de la carte impossible : " + thread.error))
            report.write(args.report)
        sys.exit(1)
    if thread.archive_path:
        print("\n" + thread.archive_path)
