from flask import render_template, Flask, Response, request, url_for, redirect, session, send_file, flash, jsonify
from flaski import app
from werkzeug.utils import secure_filename
from flask_session import Session
from flaski.forms import LoginForm
from flask_login import current_user, login_user, logout_user, login_required
from datetime import datetime
from flaski import db
from werkzeug.urls import url_parse
from flaski.apps.main.violinplot import make_figure, figure_defaults
from flaski.models import User, UserLogging
from flaski.routines import session_to_file, check_session_app, handle_exception, read_request, read_tables, allowed_file, read_argument_file, read_session_file
from flaski.email import send_exception_email

import os
import io
import sys
import random
import json

import matplotlib
matplotlib.use('agg')
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_svg import FigureCanvasSVG
from pandas.api.types import is_numeric_dtype
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

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

@app.route('/violinplot/<download>', methods=['GET', 'POST'])
@app.route('/violinplot', methods=['GET', 'POST'])
@login_required
def violinplot(download=None):
    
    apps=current_user.user_apps
    plot_arguments=None  

    reset_info=check_session_app(session,"violinplot",apps)

    if reset_info:
        flash(reset_info,'error')
        # INITIATE SESSION
        session["filename"]="Select file.."
        plot_arguments=figure_defaults()
        session["plot_arguments"]=plot_arguments
        session["COMMIT"]=app.config['COMMIT']
        session["app"]="violinplot"
           
    if request.method == 'POST' :
        try:
            if request.files["inputsessionfile"] :
                msg, plot_arguments, error=read_session_file(request.files["inputsessionfile"],"violinplot")
                if error:
                    flash(msg,'error')
                    return render_template('/apps/violinplot.html' , filename=session["filename"],apps=apps, **plot_arguments)
                flash(msg,"info")

            if request.files["inputargumentsfile"] :
                msg, plot_arguments, error=read_argument_file(request.files["inputargumentsfile"],"violinplot")
                if error:
                    flash(msg,'error')
                    return render_template('/apps/violinplot.html' , filename=session["filename"], apps=apps, **plot_arguments)
                flash(msg,"info")
            
            # IF THE USER UPLOADS A NEW FILE
            # THEN UPDATE THE SESSION FILE
            # READ INPUT FILE
            inputfile = request.files["inputfile"]
            if inputfile:
                filename = secure_filename(inputfile.filename)
                if allowed_file(inputfile.filename):

                    df=read_tables(inputfile)
                    cols=df.columns.tolist()
                    vals=[None]+cols
                                    
                    # sometext="Please select at least one numeric column to create your violin plot."
                    session["plot_arguments"]["cols"]=cols
                    session["plot_arguments"]["vals"]=vals
                    plot_arguments=session["plot_arguments"]
                    # plot_arguments=read_request(request)

                    # flash(sometext,'info')
                    return render_template('/apps/violinplot.html' , filename=filename, apps=apps,**plot_arguments)
                    
                else:
                    # IF UPLOADED FILE DOES NOT CONTAIN A VALID EXTENSION PLEASE UPDATE
                    error_msg="You can can only upload files with the following extensions: 'xlsx', 'tsv', 'csv'. Please make sure the file '%s' \
                    has the correct format and respective extension and try uploadling it again." %filename
                    flash(error_msg,'error')
                    return render_template('/apps/violinplot.html' , filename=session["filename"], apps=apps, **plot_arguments)
            
            if "df" not in list(session.keys()):
                error_msg="No data to plot, please upload a data or session  file."
                flash(error_msg,'error')
                return render_template('/apps/violinplot.html' , filename="Select file..", apps=apps,  **plot_arguments)
            
            # USER INPUT/PLOT_ARGUMENTS GETS UPDATED TO THE LATEST INPUT
            plot_arguments=read_request(request)
            # vals=request.form.getlist("vals")
            vals=plot_arguments["vals"]
            df=pd.read_json(session["df"])
            filename=session["filename"]

            #IN CASE THE USER HAS NOT SELECTED X_VAL or Y_VAL
            if  plot_arguments["x_val"] == "None" or plot_arguments["y_val"]=="None":
                sometext="Please select a valid value to plot in your X and Y axes"
                plot_arguments=session["plot_arguments"]
                plot_arguments["vals"]=vals
                flash(sometext,'info')
                return render_template('/apps/iviolinplot.html' , filename=filename, apps=apps,**plot_arguments)


            #IN CASE THE USER HAS UNSELECTED ALL THE COLUMNS THAT WE NEED TO PLOT THE VIOLINPLOT
            if  vals == []:
                sometext="Please select at least one numeric column from which we will plot your violinplot"
                plot_arguments=session["plot_arguments"]
                plot_arguments["vals"]=vals
                flash(sometext,'info')
                return render_template('/apps/violinplot.html' , filename=filename, apps=apps,**plot_arguments)
                
            #VERIFY THERE IS AT LEAST ONE NUMERIC COLUMN SELECTED BY THE USER
            vals_copy=vals.copy()
            vals_copy.remove(None)
            if not any(df[vals_copy].dtypes.apply(is_numeric_dtype)):
                sometext="Remember that at least one of the columns you select has to be numeric"
                session["plot_arguments"]["vals"]=[None]+vals
                plot_arguments=session["plot_arguments"]
                plot_arguments["vals"]=vals
                flash(sometext,'info')
                return render_template('/apps/violinplot.html' , filename=filename, apps=apps,**plot_arguments)
            
                # #IF THE USER HAS CHANGED THE COLUMNS TO PLOT
                # if vals+["None"] != plot_arguments["vals"]:
                #     plot_arguments=figure_defaults()
                #     cols=df.columns.tolist()                   
                #     plot_arguments["vals"]=vals+["None"]
                #     plot_arguments["cols"]=cols
                #     session["plot_arguments"]=plot_arguments 
                #     sometext="Please tweak the arguments of your violin plot"
                #     flash(sometext,'info')
                #     return render_template('/apps/violinplot.html' , filename=filename, apps=apps,**plot_arguments)

            session["plot_arguments"]=plot_arguments


            # MAKE SURE WE HAVE THE LATEST ARGUMENTS FOR THIS SESSION
            #filename=session["filename"]
            #plot_arguments=session["plot_arguments"]
            #plot_arguments["vals"]=vals
            #session["plot_arguments"]["vals"]=vals+["None"]


            fig=make_figure(df,plot_arguments)

            #TRANSFORM FIGURE TO BYTES AND BASE64 STRING
            figfile = io.BytesIO()
            plt.savefig(figfile, format='png')
            plt.close()
            figfile.seek(0)  # rewind to beginning of file
            figure_url = base64.b64encode(figfile.getvalue()).decode('utf-8')
            return render_template('/apps/violinplot.html', figure_url=figure_url, filename=filename, apps=apps, **plot_arguments)

        except Exception as e:
            tb_str=handle_exception(e,user=current_user,eapp="violinplot",session=session)
            flash(tb_str,'traceback')
            if not plot_arguments:
                plot_arguments=session["plot_arguments"]
            return render_template('/apps/violinplot.html', filename=session["filename"], apps=apps, **session["plot_arguments"])

    else:
        if download == "download":
            # READ INPUT DATA FROM SESSION JSON
            df=pd.read_json(session["df"])

            plot_arguments=session["plot_arguments"]

            # CALL FIGURE FUNCTION
            fig=make_figure(df,plot_arguments)

            figfile = io.BytesIO()
            mimetypes={"png":'image/png',"pdf":"application/pdf","svg":"image/svg+xml"}
            plt.savefig(figfile, format=plot_arguments["downloadf"])
            plt.close()
            figfile.seek(0)  # rewind to beginning of file

            eventlog = UserLogging(email=current_user.email,action="download figure violinplot")
            db.session.add(eventlog)
            db.session.commit()

            return send_file(figfile, mimetype=mimetypes[plot_arguments["downloadf"]], as_attachment=True, attachment_filename=plot_arguments["downloadn"]+"."+plot_arguments["downloadf"] )
       
        return render_template('apps/violinplot.html',  filename=session["filename"], apps=apps, **session["plot_arguments"])

