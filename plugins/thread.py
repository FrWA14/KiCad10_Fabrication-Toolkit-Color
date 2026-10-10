# Modified 2026 by Fabrication Toolkit Color: JLCPCB multi-colour silkscreen support (see NOTICE).
import os
import wx
import pcbnew  # type: ignore
import shutil
import tempfile
import webbrowser
import datetime
import logging
from threading import Thread
from .events import StatusEvent
from .process import ProcessManager
from .config import *
from .options import *
from .utils import print_cli_progress_bar
from .color_silkscreen.errors import ColorSilkError
from .color_silkscreen.report import Report, setup_logging


class ProcessThread(Thread):
    def __init__(self, wx, options, cli = None, openBrowser = True, nonInteractive = False):
        Thread.__init__(self)
        self.error = None
        self.archive_path = None

        # prevent use of cli and graphical mode at the same time
        if (wx is None and cli is None) or (wx is not None and cli is not None):
            logging.error("Specify either graphical or cli use!")
            self.error = "Specify either graphical or cli use!"
            return

        if cli is not None:
            try:
                self.board = pcbnew.LoadBoard(cli)
            except Exception as e:
                logging.error("Fabrication Toolkit - Error" + str(e))
                self.error = str(e)
                return
        else:
            self.board = None
            
        self.process_manager = ProcessManager(self.board)
        self.wx = wx
        self.cli = cli
        self.options = options
        self.openBrowser = openBrowser
        self.nonInteractive = nonInteractive
        self.start()

    def expandTextVariables(self, string):
        board = self.board if self.board is not None else pcbnew.GetBoard()
        titleBlock = board.GetTitleBlock()

        titleBlockVars = {
            "ISSUE_DATE": titleBlock.GetDate(),
            "CURRENT_DATE": datetime.datetime.now().strftime('%Y-%m-%d'),
            "REVISION": titleBlock.GetRevision(),
            "TITLE": titleBlock.GetTitle(),
            "COMPANY": titleBlock.GetCompany(),
        }

        for comment_index in range(9):
            titleBlockVars[f"COMMENT{comment_index + 1}"] = titleBlock.GetComment(comment_index)

        for var, val in titleBlockVars.items():
            string = string.replace(f"${{{var}}}", val)

        if (hasattr(self.process_manager.board, "GetProject") and hasattr(pcbnew, "ExpandTextVars")):
            project = self.process_manager.board.GetProject()
            string = pcbnew.ExpandTextVars(string, project)

        return string


    def run(self):
        # initializing
        self.progress(0)

        temp_dir = tempfile.mkdtemp()
        temp_dir_gerber = temp_dir + "_g"
        os.makedirs(temp_dir_gerber)

        _, temp_file = tempfile.mkstemp()
        project_directory = os.path.dirname(self.process_manager.board.GetFileName())

        color_report = self.start_color_report(project_directory)

        try:
            # Verify all zones are up-to-date
            self.progress(10)
            if (self.options[AUTO_FILL_OPT]):
                self.process_manager.update_zone_fills()

            # generate gerber
            self.progress(20)
            self.process_manager.generate_gerber(temp_dir_gerber, self.options[EXTRA_LAYERS], self.options[EXTEND_EDGE_CUT_OPT],
                                                 self.options[ALTERNATIVE_EDGE_CUT_OPT], self.options[ALL_ACTIVE_LAYERS_OPT])

            # generate drill file
            self.progress(30)
            self.process_manager.generate_drills(temp_dir_gerber)

            # colour silkscreen: EasyEDA-style Gerbers + encrypted colour files
            if color_report is not None:
                self.progress(35)
                self.generate_color_silkscreen(temp_dir_gerber, color_report)

            # generate netlist
            self.progress(40)
            self.process_manager.generate_netlist(temp_dir)

            # generate data tables
            self.progress(50)
            self.process_manager.generate_tables(temp_dir, self.options[AUTO_TRANSLATE_OPT], self.options[EXCLUDE_DNP_OPT])

            # generate pick and place file
            self.progress(60)
            self.process_manager.generate_positions(temp_dir)

            # generate BOM file
            self.progress(70)
            self.process_manager.generate_bom(temp_dir)

            # generate production archive
            self.progress(85)
            temp_file = self.process_manager.generate_archive(temp_dir_gerber, temp_file)
            shutil.move(temp_file, temp_dir)
            shutil.rmtree(temp_dir_gerber)
            temp_file = os.path.join(temp_dir, os.path.basename(temp_file))
        except Exception as e:
            self.error = str(e)
            message = e.user_text() if isinstance(e, ColorSilkError) else str(e)
            if color_report is not None:
                color_report.error(e if isinstance(e, ColorSilkError) else ColorSilkError("E_INTERNAL", str(e)))
                self.finish_color_report(color_report)
            if self.wx is None:
                logging.error("Fabrication Toolkit - Error" + str(e))
            else:
                wx.MessageBox(message, "Fabrication Toolkit - Error", wx.OK | wx.ICON_ERROR)
            self.progress(-1)
            return

        # progress bar done animation
        read_so_far = 0
        total_size = os.path.getsize(temp_file)
        with open(temp_file, 'rb') as file:
            while True:
                data = file.read(10)
                if not data:
                    break
                read_so_far += len(data)
                percent = read_so_far * 1e2 / total_size
                self.progress(85 + percent / 8)

        # generate gerber name
        title_block = self.process_manager.board.GetTitleBlock()
        title = title_block.GetTitle()
        revision = title_block.GetRevision()
        company = title_block.GetCompany()
        file_date = title_block.GetDate()

        if (hasattr(self.process_manager.board, "GetProject") and hasattr(pcbnew, "ExpandTextVars")):
            project = self.process_manager.board.GetProject()
            title = pcbnew.ExpandTextVars(title, project)
            revision = pcbnew.ExpandTextVars(revision, project)
            company = pcbnew.ExpandTextVars(company, project)
            file_date = pcbnew.ExpandTextVars(file_date, project)

        # make output dir
        filename = os.path.splitext(os.path.basename(self.process_manager.board.GetFileName()))[0]
        output_path = os.path.join(project_directory, outputFolder)
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        
        # rename gerber archive
        if self.options[ARCHIVE_NAME]:
            baseName = self.expandTextVariables(self.options[ARCHIVE_NAME])
        else:
            baseName = "{} {}".format(title or filename, revision or '')

        gerberArchiveName = ProcessManager.normalize_filename("_".join((baseName.strip() + '.zip').split()))
        os.rename(temp_file, os.path.join(temp_dir, gerberArchiveName))

        if self.options[ARCHIVE_NAME]:
            if os.path.exists(os.path.join(temp_dir, designatorsFileName)):
                os.rename(os.path.join(temp_dir, designatorsFileName), os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + '_designators.csv').split()))))
            if os.path.exists(os.path.join(temp_dir, placementFileName)):
                os.rename(os.path.join(temp_dir, placementFileName), os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + '_positions.csv').split()))))
            if os.path.exists(os.path.join(temp_dir, bomFileName)):
                os.rename(os.path.join(temp_dir, bomFileName), os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + '_bom.csv').split()))))

        # Make a backup as long as the BACKUP_OPT flag is set.
        if self.options[BACKUP_OPT]:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
            backup_name = ProcessManager.normalize_filename("_".join(("{} {}".format(baseName, timestamp).strip()).split()))
            shutil.make_archive(os.path.join(output_path, 'backups', backup_name), 'zip', temp_dir)

        # copy to & open output dir
        try:
            shutil.copytree(temp_dir, output_path, dirs_exist_ok=True)
            if self.openBrowser:
                webbrowser.open("file://%s" % (output_path))
            shutil.rmtree(temp_dir)
        except Exception as e:
            if self.openBrowser:
                webbrowser.open("file://%s" % (temp_dir))

        self.archive_path = os.path.join(output_path, gerberArchiveName)
        if color_report is not None:
            self.record_archive(color_report)
            checks = self.check_and_preview(color_report)
            self.finish_color_report(color_report)
            if self.wx is not None:
                from .export_viewer import show_export_viewer
                wx.CallAfter(show_export_viewer, self.archive_path, getattr(self, "color_composites", {}), checks,
                             color_report.data["warnings"])
            elif checks is not None:
                for c in checks:
                    print("{} {} - {}".format("OK " if c["ok"] else "NOK", c["code"], c["message"]))

        if self.wx is None:
            self.progress(100)
        else:
            self.progress(-1)

    """ Colour silkscreen """

    def color_requested(self):
        silk = any((self.options.get(k) or {}).get("enabled") for k in (TOP_SILK_OPT, BOTTOM_SILK_OPT))
        return silk or bool(self.options.get(COLOR_CALIBRATION_OPT)) or any(self.options.get(k) for k in (TOP_IMAGE_OPT, BOTTOM_IMAGE_OPT, TOP_PLACEMENT_OPT, BOTTOM_PLACEMENT_OPT))

    def start_color_report(self, project_directory):
        if not self.color_requested():
            return None
        out_dir = os.path.join(project_directory, outputFolder)
        self.color_out_dir = out_dir
        self.color_report_path = self.options.get(COLOR_REPORT_OPT) or os.path.join(out_dir, 'color_silkscreen_report.json')
        self.color_log_path = self.options.get(COLOR_LOG_OPT) or os.path.join(out_dir, 'color_silkscreen.log')
        setup_logging(self.color_log_path, console=self.wx is None)
        return Report(input_board=self.process_manager.board.GetFileName(), kicad_version=pcbnew.Version())

    def finish_color_report(self, report):
        try:
            report.write(self.color_report_path)
        except OSError as e:
            logging.error("Fabrication Toolkit - cannot write colour report: " + str(e))

    def board_edge_bounds_mm(self):
        '''Edge.Cuts bounding box expressed in Gerber coordinates (aux origin, Y up).'''
        board = self.process_manager.board
        bbox = board.GetBoardEdgesBoundingBox()
        if bbox.GetWidth() <= 0 or bbox.GetHeight() <= 0:
            return None
        aux = board.GetDesignSettings().GetAuxOrigin()
        to_mm = pcbnew.ToMM
        return (to_mm(bbox.GetLeft() - aux.x), -to_mm(bbox.GetBottom() - aux.y),
                to_mm(bbox.GetRight() - aux.x), -to_mm(bbox.GetTop() - aux.y))

    def generate_color_silkscreen(self, gerber_dir, report):
        from .color_silkscreen.generate import generate_color_silkscreen, Options

        expected = None
        if not self.options.get(ALTERNATIVE_EDGE_CUT_OPT) and not self.options.get(EXTEND_EDGE_CUT_OPT):
            expected = self.board_edge_bounds_mm()
        report.step("gerbers", files=sorted(os.listdir(gerber_dir)))
        images = self.compose_placed_images(report)
        generate_color_silkscreen(
            gerber_dir,
            top_image=images["top"],
            bottom_image=images["bottom"],
            report=report,
            options=Options(fit=self.options.get(COLOR_FIT_OPT) or "stretch",
                            profile=self.options.get(COLOR_PROFILE_OPT) or "default",
                            debug_svg_dir=self.options.get(COLOR_DEBUG_SVG_OPT) or None,
                            eda_version=self.options.get(COLOR_EDA_VERSION_OPT) or None,
                            easyeda_version=self.options.get(COLOR_EASYEDA_VERSION_OPT) or None,
                            blank_silk_sides=self.silk_printed_sides(),
                            expected_bounds_mm=expected))

    def silk_printed_sides(self):
        if self.options.get(COLOR_CALIBRATION_OPT):
            return ()
        return tuple(side for side, key in (("top", TOP_SILK_OPT), ("bottom", BOTTOM_SILK_OPT))
                     if (self.options.get(key) or {}).get("enabled") and not (self.options.get(key) or {}).get("keep_classic"))

    def compose_placed_images(self, report):
        '''Placed images and/or silkscreen-as-image -> board-sized 1200 DPI composites
        clipped to Edge.Cuts. Sides with neither keep the plain image (fitted to the outline box).'''
        from .color_silkscreen import board_view, placement as pl

        images = {"top": self.options.get(TOP_IMAGE_OPT) or None, "bottom": self.options.get(BOTTOM_IMAGE_OPT) or None}
        self.color_composites = {}
        for stale in ("top", "bottom"):  # never preview/encrypt a composite left by a previous export
            for ext in ("png", "jpg"):
                old = os.path.join(self.color_out_dir, "color_{}_composite.{}".format(stale, ext))
                if os.path.exists(old):
                    os.remove(old)
        placements = {"top": pl.normalize(self.options.get(TOP_PLACEMENT_OPT)),
                      "bottom": pl.normalize(self.options.get(BOTTOM_PLACEMENT_OPT))}
        silk = {"top": pl.normalize_silk(self.options.get(TOP_SILK_OPT)),
                "bottom": pl.normalize_silk(self.options.get(BOTTOM_SILK_OPT))}
        offsets = {"top": pl.normalize_offset(self.options.get(TOP_OFFSET_OPT)),
                   "bottom": pl.normalize_offset(self.options.get(BOTTOM_OFFSET_OPT))}
        calibration = bool(self.options.get(COLOR_CALIBRATION_OPT))
        shifted = any(offsets[s] != (0.0, 0.0) and (images[s] or silk[s]) for s in ("top", "bottom"))
        if not any(images.values()) and not any(placements.values()) and not any(silk.values()) and not calibration:
            return images
        # Every face with artwork goes through the compositor: it clips to Edge.Cuts and
        # cuts the image on bare copper and drilled holes (on top of the SVG clip).
        if calibration:
            report.warn({"code": "W_CALIBRATION",
                         "message": "Mire de calage : les images sont remplacées par la mire sur les deux faces."})
        if self.options.get(ALTERNATIVE_EDGE_CUT_OPT):
            report.warn({"code": "W_PLACEMENT_ALT_EDGE",
                         "message": "Placement calculé sur Edge.Cuts alors que User.2 sert de contour."})
        view = board_view.extract(self.process_manager.board)
        for side in ("top", "bottom"):
            p = placements[side]
            if p and images[side] and os.path.normcase(os.path.abspath(images[side])) != os.path.normcase(os.path.abspath(p["image"])):
                report.warn({"code": "W_PLACEMENT_IGNORED",
                             "message": "Placement {} ignoré : il concerne {} et non {}.".format(
                                 side, os.path.basename(p["image"]), os.path.basename(images[side]))})
                p = None
            source = (p or {}).get("image") or images[side]
            if source and not calibration:
                # Validate the source picture itself (format, size, missing file) before composing.
                from .color_silkscreen.image import load_image
                checks = []
                load_image(source, view["width"], view["height"], checks, self.options.get(COLOR_FIT_OPT) or "stretch")
                ignore = {"W_IMAGE_LOW_DPI"} | ({"W_IMAGE_ASPECT", "W_IMAGE_PADDED"} if p else set())
                for w in checks:
                    if w["code"] not in ignore:
                        report.warn(w)
            if calibration:
                p = None
            elif not p and images[side]:
                # plain image + silkscreen: the image covers the outline box like before
                from PIL import Image
                with Image.open(images[side]) as im:
                    size = im.size
                if (self.options.get(COLOR_FIT_OPT) or "stretch") == "contain":
                    p = dict(pl.fit(view, size, 0, "contain"), image=images[side])
                else:
                    p = {"image": images[side], "cx": view["width"] / 2, "cy": view["height"] / 2,
                         "w": view["width"], "h": view["height"], "rot": 0}
            if not p and not silk[side] and not calibration:
                continue
            if silk[side] and not view["silk"][side]:
                report.warn({"code": "W_NO_SILKSCREEN",
                             "message": "Aucune sérigraphie sur la face {} : rien à imprimer en couleur.".format(side)})
            dpi = None
            if p:
                from PIL import Image
                with Image.open(p["image"]) as im:
                    dpi = pl.effective_dpi(p, im.size)
            canvas = pl.compose(view, side, p, silk=silk[side], offset=offsets[side], calibration=calibration)
            path, preview = pl.save_composite(canvas, self.color_out_dir, side)
            self.color_composites[side] = preview
            report.step("compose_" + side, image=p["image"] if p else None, placement_mm=p,
                        source_dpi=round(dpi, 1) if dpi else None, silk=silk[side],
                        silk_shapes=len(view["silk"][side]), offset_mm=list(offsets[side]),
                        calibration=calibration, composite=path, pixels=list(canvas.size))
            if dpi is not None and dpi < 150:
                report.warn({"code": "W_IMAGE_LOW_DPI",
                             "message": "Image {} imprimée à {:.0f} DPI effectifs (< 150) : rendu flou probable.".format(side, dpi)})
            images[side] = path
        pl.save_placements(os.path.join(self.color_out_dir, "color_placement.json"), placements, view, silk)
        return images

    def check_and_preview(self, report):
        '''Pre-flight checks of the final ZIP + JLCPCB-style previews (production/preview_*.png).'''
        from .color_silkscreen import export_preview, precheck
        try:
            files = export_preview.read_zip(self.archive_path)
            from PIL import Image
            composites = {s: Image.open(p) for s, p in getattr(self, "color_composites", {}).items()}
            colour_sides = tuple(s for s in ("top", "bottom")
                                 if any(n.endswith(".FCTS" if s == "top" else ".FCBS") for n in files)
                                 or s in composites)
            checks = precheck.run(files, os.path.getsize(self.archive_path), colour_sides,
                                  self.silk_printed_sides(), composites)
            errors, warnings = precheck.summary(checks)
            report.step("precheck", ok=not errors, checks=checks)
            for c in errors:
                report.error(ColorSilkError("E_PRECHECK", "{} : {}".format(c["code"], c["message"]),
                                            "Le ZIP risque d'être refusé ou sans couleur chez JLCPCB ; voir le rapport."))
            if errors:
                self.error = "pré-contrôle : " + "; ".join(c["code"] for c in errors)
            out_dir = os.path.dirname(self.archive_path)
            export_preview.render_zip(self.archive_path, getattr(self, "color_composites", {}), out_dir)
            report.step("preview", files=["preview_top.png", "preview_bottom.png"])
            return checks
        except Exception as e:
            report.warn({"code": "W_PREVIEW", "message": "Pré-contrôle / aperçu impossible : {}".format(e)})
            return None

    def record_archive(self, report):
        import zipfile
        try:
            with zipfile.ZipFile(self.archive_path) as archive:
                names = archive.namelist()
            report.step("zip", path=self.archive_path, files=names)
        except Exception as e:
            report.error(ColorSilkError("E_ZIP", "Archive {} illisible : {}".format(self.archive_path, e)))

    def progress(self, percent):
        if self.wx is None:
            if not self.nonInteractive:
                print_cli_progress_bar(percent, prefix = 'Progress:', suffix = 'Complete', length = 50)
        else:
            wx.PostEvent(self.wx, StatusEvent(percent))
