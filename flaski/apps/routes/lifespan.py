from flask import render_template, Flask, Response, request, url_for, redirect, session, send_file, flash, jsonify
from flaski import app
from werkzeug.utils import secure_filename
from flask_session import Session
from flaski.forms import LoginForm
from flask_login import current_user, login_user, logout_user, login_required
from datetime import datetime
from flaski import db
from werkzeug.urls import url_parse
from flaski.apps.main.lifespan import make_figure, figure_defaults
from flaski.apps.main import iscatterplot
from flaski.models import User, UserLogging
from flaski.routines import session_to_file, check_session_app, handle_exception, read_request, read_tables, allowed_file, read_argument_file, read_session_file, separate_apps
import plotly
import plotly.io as pio
import matplotlib.pyplot as plt
from flaski.email import send_exception_email

import os
import io
import sys
import random
import json

import pandas as pd

import base64

@app.after_request
def add_header(r):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Cache-Control'] = 'public, max-age=0'
    return r

def nFormat(x):
    try:
        if float(x) == 0:
            return str(x)
        elif ( float(x) < 0.01 ) & ( float(x) > -0.01 ) :
            return str('{:.3e}'.format(float(x)))
        else:
            return str('{:.3f}'.format(float(x)))
    except ValueError:
        return str(x)

@app.route('/lifespan/<download>', methods=['GET', 'POST'])
@app.route('/lifespan', methods=['GET', 'POST'])
@login_required
def lifespan(download=None):

    apps=current_user.user_apps
    plot_arguments=None  


    reset_info=check_session_app(session,"lifespan",apps)

    submissions, apps=separate_apps(current_user.user_apps)


    if reset_info:
        flash(reset_info,'error')
        # INITIATE SESSION
        session["filename"]="Select file.."
        plot_arguments=figure_defaults()
        session["plot_arguments"]=plot_arguments
        session["COMMIT"]=app.config['COMMIT']
        session["app"]="lifespan"

    if request.method == 'POST':

        try:
            if request.files["inputsessionfile"] :
                msg, plot_arguments, error=read_session_file(request.files["inputsessionfile"],"lifespan")
                if error:
                    flash(msg,'error')
                    return render_template('/apps/lifespan.html' , filename=session["filename"],apps=apps, **plot_arguments)
                flash(msg,"info")

            if request.files["inputargumentsfile"] :
                msg, plot_arguments, error=read_argument_file(request.files["inputargumentsfile"],"lifespan")
                if error:
                    flash(msg,'error')
                    return render_template('/apps/lifespan.html' , filename=session["filename"], apps=apps, **plot_arguments)
                flash(msg,"info")
            
            # IF THE UPLOADS A NEW FILE 
            # THAN UPDATE THE SESSION FILE
            # READ INPUT FILE
            inputfile = request.files["inputfile"]
            if inputfile:
                filename = secure_filename(inputfile.filename)
                if allowed_file(inputfile.filename):
                    df=read_tables(inputfile) 
                    cols=df.columns.tolist()

                    if session["plot_arguments"]["censors_col"] not in cols:
                        session["plot_arguments"]["censors_col"] = ["None"]+cols

                    if session["plot_arguments"]["groups"] not in cols:
                        session["plot_arguments"]["groups"] = ["None"]+cols

                    # IF THE USER HAS NOT YET CHOOSEN X AND Y VALUES THAN PLEASE SELECT
                    if (session["plot_arguments"]["yvals"] not in cols):

                        session["plot_arguments"]["xcols"]=cols
                        session["plot_arguments"]["xvals"]=cols[0]

                        session["plot_arguments"]["ycols"]=cols
                        session["plot_arguments"]["yvals"]=cols[1:]
                                  
                        sometext="Please select which columns should be used for plotting."
                        plot_arguments=session["plot_arguments"]
                        flash(sometext,'info')
                        return render_template('/apps/lifespan.html' , filename=filename, apps=apps, **plot_arguments)
                    
                else:
                    # IF UPLOADED FILE DOES NOT CONTAIN A VALID EXTENSION PLEASE UPDATE
                    error_msg="You can can only upload files with the following extensions: 'xlsx', 'tsv', 'csv'. Please make sure the file '%s' \
                    has the correct format and respective extension and try uploadling it again." %filename
                    flash(error_msg,'error')
                    return render_template('/apps/lifespan.html' , filename="Select file..", apps=apps, **plot_arguments)

            if not request.files["inputsessionfile"] and not request.files["inputargumentsfile"] :

                # USER INPUT/PLOT_ARGUMENTS GETS UPDATED TO THE LATEST INPUT
                # WITH THE EXCEPTION OF SELECTION LISTS
                plot_arguments = session["plot_arguments"]

                if plot_arguments["groups_value"]!=request.form["groups_value"]:
                    if request.form["groups_value"]  != "None":
                        df=pd.read_json(session["df"])
                        df[request.form["groups_value"]]=df[request.form["groups_value"]].apply(lambda x: secure_filename(str(x) ) )
                        df=df.astype(str)
                        session["df"]=df.to_json()
                        groups=df[request.form["groups_value"]]
                        groups=list(set(groups))
                        groups.sort()
                        plot_arguments["list_of_groups"]=groups
                        groups_settings=[]
                        group_dic={}
                        for group in groups:
                            group_dic={"name":group,\
                                "censor_marker_value":plot_arguments["censor_marker_value"], \
                                "censor_marker_size_val":plot_arguments["censor_marker_size_val"], \
                                "edgecolor":plot_arguments["edgecolor"], \
                                "edgecolor_write":"", \
                                "edge_linewidth":plot_arguments["edge_linewidth"], \
                                "markerc":plot_arguments["markerc"], \
                                "markerc_write":"", \
                                "marker_alpha":plot_arguments["marker_alpha"], \
                                "ci_alpha":plot_arguments["ci_alpha"], \
                                "linestyle_value":plot_arguments["linestyle_value"], \
                                "linestyle_write":"", \
                                "linewidth_write":plot_arguments["linewidth_write"], \
                                "line_color_value":plot_arguments["line_color_value"],\
                                "linecolor_write":"", \
                                "show_censors":plot_arguments["show_censors"], \
                                "Conf_Interval":plot_arguments["Conf_Interval"], \
                                "ci_legend":plot_arguments["ci_legend"], \
                                "ci_force_lines":plot_arguments["ci_force_lines"]}  
                            groups_settings.append(group_dic)
                        plot_arguments["groups_settings"]=groups_settings
                    elif request.form["groups_value"] == "None" :
                        plot_arguments["groups_settings"]=[]
                        plot_arguments["list_of_groups"]=[]
                        

                elif plot_arguments["groups_value"] != "None":
                    groups_settings=[]
                    group_dic={}
                    for group in plot_arguments["list_of_groups"]:
                        group_dic={"name":group,\
                            "censor_marker_value":request.form["%s.censor_marker_value" %group], \
                            "censor_marker_size_val":request.form["%s.censor_marker_size_val" %group], \
                            "edgecolor":request.form["%s.edgecolor" %group], \
                            "edgecolor_write":request.form["%s.edgecolor_write" %group], \
                            "edge_linewidth":request.form["%s.edge_linewidth" %group], \
                            "markerc":request.form["%s.markerc" %group], \
                            "markerc_write":request.form["%s.markerc_write" %group], \
                            "marker_alpha":request.form["%s.marker_alpha" %group], \
                            "ci_alpha":request.form["%s.ci_alpha" %group], \
                            "linestyle_value":request.form["%s.linestyle_value" %group], \
                            "linestyle_write":request.form["%s.linestyle_write" %group], \
                            "linewidth_write":request.form["%s.linewidth_write" %group], \
                            "line_color_value":request.form["%s.line_color_value" %group],\
                            "linecolor_write":request.form["%s.linecolor_write" %group]
                        }
                        
                        if request.form.get("%s.show_censors" %group) == 'on':
                            group_dic["show_censors"]='on'
                        else:
                            group_dic["show_censors"]='off'
                        if request.form.get("%s.Conf_Interval" %group) == 'on':
                            group_dic["Conf_Interval"]='on'
                        else:
                            group_dic["Conf_Interval"]='off'
                        if request.form.get("%s.ci_legend" %group) == 'on':
                            group_dic["ci_legend"]='on'
                        else:
                            group_dic["ci_legend"]='off'
                        if request.form.get("%s.ci_force_lines" %group) == 'on':
                            group_dic["ci_force_lines"]='on'
                        else:
                            group_dic["ci_force_lines"]='off'

                        groups_settings.append(group_dic)
                    plot_arguments["groups_settings"]=groups_settings

                session["plot_arguments"]=plot_arguments
                plot_arguments=read_request(request)

    
            if "df" not in list(session.keys()):
                error_message="No data to plot, please upload a data or session  file."
                flash(error_message,'error')
                return render_template('/apps/lifespan.html' , filename="Select file..", apps=apps,  **plot_arguments)


            # MAKE SURE WE HAVE THE LATEST ARGUMENTS FOR THIS SESSION
            filename=session["filename"]
            plot_arguments=session["plot_arguments"]

            # READ INPUT DATA FROM SESSION JSON
            df=pd.read_json(session["df"])
            
            # CALL FIGURE FUNCTION
            # try:
            if str(plot_arguments["groups_value"]) == "None":
                df_ls, fig=make_figure(df,plot_arguments)

                df_ls=df_ls.astype(str)
                session["df_ls"]=df_ls.to_json()

                # TRANSFORM FIGURE TO BYTES AND BASE64 STRING
                figfile = io.BytesIO()
                plt.savefig(figfile, format='png')
                plt.close()
                figfile.seek(0)  # rewind to beginning of file
                figure_url = base64.b64encode(figfile.getvalue()).decode('utf-8')

                #return render_template('/apps/lifespan.html', figure_url=figure_url, filename=filename, apps=apps, **plot_arguments)

                df_selected=df_ls[:50]
                cols_to_format=df_selected.columns.tolist()
                table_headers=cols_to_format

                for c in cols_to_format:
                    df_selected[c]=df_selected[c].apply(lambda x: nFormat(x) )

                df_selected=list(df_selected.values)
                df_selected=[ list(s) for s in df_selected ]

                return render_template('/apps/lifespan.html', figure_url=figure_url, table_headers=table_headers, table_contents=df_selected, filename=filename, apps=apps, **plot_arguments)

            elif str(plot_arguments["groups_value"]) != "None":
                df_ls, fig, cph_stats, cph_coeffs=make_figure(df,plot_arguments)

                df_ls=df_ls.astype(str)
                session["df_ls"]=df_ls.to_json()

                cph_stats=cph_stats.astype(str)
                session["cph_stats"]=cph_stats.to_json()

                cph_coeffs=cph_coeffs.astype(str)
                session["cph_coeffs"]=cph_coeffs.to_json()

                # TRANSFORM FIGURE TO BYTES AND BASE64 STRING
                figfile = io.BytesIO()
                plt.savefig(figfile, format='png')
                plt.close()
                figfile.seek(0)  # rewind to beginning of file
                figure_url = base64.b64encode(figfile.getvalue()).decode('utf-8')

                df_selected=df_ls[:50]
                cols_to_format=df_selected.columns.tolist()
                table_headers=cols_to_format

                for c in cols_to_format:
                    df_selected[c]=df_selected[c].apply(lambda x: nFormat(x) )

                df_selected=list(df_selected.values)
                df_selected=[ list(s) for s in df_selected ]


                df_coeffs=cph_coeffs[:50]
                cols_to_format_coeffs=df_coeffs.columns.tolist()
                table_headers_coeffs=cols_to_format_coeffs

                for c in cols_to_format_coeffs:
                    df_coeffs[c]=df_coeffs[c].apply(lambda x: nFormat(x) )

                df_coeffs=list(df_coeffs.values)
                df_coeffs=[ list(s) for s in df_coeffs ]

                df_stats=cph_stats[:50]
                cols_to_format_stats=df_stats.columns.tolist()
                table_headers_stats=cols_to_format_stats

                for c in cols_to_format_stats:
                    df_stats[c]=df_stats[c].apply(lambda x: nFormat(x) )

                df_stats=list(df_stats.values)
                df_stats=[ list(s) for s in df_stats ]


                return render_template('/apps/lifespan.html', figure_url=figure_url, table_headers=table_headers, table_contents=df_selected, table_headers_coeffs=table_headers_coeffs, table_contents_coeff=df_coeffs, table_headers_stats=table_headers_stats, table_contents_stats=df_stats,  filename=filename, apps=apps, **plot_arguments)


        except Exception as e:
            tb_str=handle_exception(e,user=current_user,eapp="lifespan",session=session)
            filename=session["filename"]
            flash(tb_str,'traceback')
            if not plot_arguments:
                plot_arguments=session["plot_arguments"]
            return render_template('/apps/lifespan.html', filename=filename, apps=apps, **plot_arguments)

    else:
        if download == "download":

            # READ INPUT DATA FROM SESSION JSON
            df=pd.read_json(session["df"])
            plot_arguments=session["plot_arguments"]

            if str(plot_arguments["groups_value"]) == "None":
                # CALL FIGURE FUNCTION
                df_ls, fig=make_figure(df,plot_arguments)

            elif str(plot_arguments["groups_value"]) != "None":
                # CALL FIGURE FUNCTION
                df_ls, fig, cph_coeff, cph_stats=make_figure(df,plot_arguments)

            figfile = io.BytesIO()
            mimetypes={"png":'image/png',"pdf":"application/pdf","svg":"image/svg+xml"}
            plt.savefig(figfile, format=plot_arguments["download_fig"])
            plt.close()
            figfile.seek(0)  # rewind to beginning of file

            eventlog = UserLogging(email=current_user.email,action="download figure lifespan curve")
            db.session.add(eventlog)
            db.session.commit()

            return send_file(figfile, mimetype=mimetypes[plot_arguments["download_fig"]], as_attachment=True, attachment_filename=plot_arguments["downloadn_fig"]+"."+plot_arguments["download_fig"] )

            

        if download == "results":

            # READ INPUT DATA FROM SESSION JSON
            df=pd.read_json(session["df"])
            plot_arguments=session["plot_arguments"]

            if str(plot_arguments["groups_value"]) == "None":
                # CALL FIGURE FUNCTION
                df_ls, fig=make_figure(df,plot_arguments)

            elif str(plot_arguments["groups_value"]) != "None":
                # CALL FIGURE FUNCTION
                df_ls, fig, cph_coeff, cph_stats=make_figure(df,plot_arguments)

            
            eventlog = UserLogging(email=current_user.email,action="download table survival analysis")
            db.session.add(eventlog)
            db.session.commit()

            if plot_arguments["downloadf"] == "xlsx":
                excelfile = io.BytesIO()
                EXC=pd.ExcelWriter(excelfile)
                df_ls.to_excel(EXC,sheet_name="survival_analysis", index=None)
                EXC.save()
                excelfile.seek(0)
                return send_file(excelfile, attachment_filename=plot_arguments["downloadn"]+".xlsx",as_attachment=True)

            elif plot_arguments["downloadf"] == "tsv":               
                return Response(df_ls.to_csv(sep="\t"), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=%s.tsv" %plot_arguments["downloadn"]})

        if download == "cph":

            # READ INPUT DATA FROM SESSION JSON
            df=pd.read_json(session["df"])
            plot_arguments=session["plot_arguments"]

            if str(plot_arguments["groups_value"]) != "None":
                # CALL FIGURE FUNCTION
                df_ls, fig, cph_coeff, cph_stats=make_figure(df,plot_arguments)

            eventlog = UserLogging(email=current_user.email,action="download table cox proportional hazard")
            db.session.add(eventlog)
            db.session.commit()

            if plot_arguments["downloadf"] == "xlsx":
                excelfile = io.BytesIO()
                EXC=pd.ExcelWriter(excelfile)
                cph_stats.to_excel(EXC,sheet_name="Statistics", index=None)
                cph_coeff.to_excel(EXC,sheet_name="CoxProportionalHazard_coeff", index=None)
                EXC.save()
                excelfile.seek(0)
                return send_file(excelfile, attachment_filename=plot_arguments["downloadn"]+".xlsx",as_attachment=True)

            elif plot_arguments["downloadf"] == "tsv":               
                return Response(cph_coeff.to_csv(sep="\t",mode='a'), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=%s.tsv" %plot_arguments["downloadn"]})
        
            
        return render_template('apps/lifespan.html',  filename=session["filename"], apps=apps, **session["plot_arguments"])            