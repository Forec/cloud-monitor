# 作者：Forec
# 最后修改日期：2016-12-20
# 邮箱：forec@bupt.edu.cn
# 关于此文件：此文件包含了服务器除认证外的所有的界面入口，包括首页、云盘界面、
#    文件操作、下载、聊天模块、管理员界面等。
# 蓝本：main

import os, random, shutil, os.path, json
from config       import basedir
from flask        import render_template, redirect, url_for, \
                        abort, flash, request, current_app, jsonify
from flask_login  import login_required, current_user
from .forms       import EditProfileForm, DeviceEditForm, \
                        DeviceDeleteForm, NewDeviceForm
from sqlalchemy import text
from .            import main
from ..           import db
from ..models     import User ,Pagination, Device, Record
from ..devices    import deviceTable

# ----------------------------------------------------------------
# home 函数提供了介绍界面的入口
@main.route('/')
def home():
    return render_template('home.html')

# ----------------------------------------------------------------
# index 为服务器主页入口点，将展示用户拥有的设备
@main.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    page = request.args.get('page', 1, type=int)

    deviceList = current_user.devices.all()
    pagination = Pagination(page=page,
                            per_page=current_app.\
                                config['ZENITH_DEVICES_PER_PAGE'],
                            total_count=len(deviceList))
    devices = deviceList[(page-1)*current_app.\
                            config['ZENITH_DEVICES_PER_PAGE']:
                          page*current_app.\
                            config['ZENITH_DEVICES_PER_PAGE']]
    return render_template('index/index.html',
                           devices = devices,
                           pagination = pagination)

# -------------------------------------------------------------------
# user 函数为服务器用户资料界面入口点，用户资料界面包括用户基本信息、
# 资料编辑。其中文件显示方式和 index 界面相同
@main.route('/user/<int:id>')
def user(id):
    user = User.query.filter_by(uid=id).first()
    if user is None:
        abort(404)
    return render_template('main/profile/user.html',
                           user = user)

# -----------------------------------------------------------------------
# edit_profile 为当前已登陆用户提供编辑用户资料入口
@main.route('/edit-profile', methods=['GET','POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        # 验证上传头像的合法性
        if form.thumbnail.has_file():
            while True:
                # 创建随机目录
                randomBasePath = current_app.\
                    config['ZENITH_TEMPFILE_STORE_PATH'] + \
                    ''.join(random.sample(
                            current_app.\
                                config['ZENITH_RANDOM_PATH_ELEMENTS'],
                            current_app.\
                                config['ZENITH_TEMPFOLDER_LENGTH']))
                if os.path.exists(randomBasePath):
                # 若创建的随机目录已存在则重新创建
                    continue
                break
            os.mkdir(randomBasePath)
            if not os.path.exists(randomBasePath):
                abort(500)
            filepath = os.path.join(randomBasePath,
                                    form.thumbnail.data.filename)
            suffix = form.thumbnail.data.filename
            # 判断后缀名是否合法
            suffix = suffix.split('.')
            if len(suffix) < 2 or '.' + suffix[-1] not in \
                current_app.config['ZENITH_VALID_THUMBNAIL']:
                flash('您上传的头像不符合规范！')
                os.rmdir(randomBasePath)
                return redirect(url_for('main.edit_profile',
                                        _external=True))
            suffix = '.' + suffix[-1]     # suffix 为后缀名

            form.thumbnail.data.save(filepath)
            if not os.path.isfile(filepath):
                abort(500)
            if os.path.getsize(filepath) > \
                current_app.config['ZENITH_VALID_THUMBNAIL_SIZE']:
                # 头像大小大于 512KB
                flash('您上传的头像过大，已被系统保护性删除，请保证'
                      '上传的头像文件大小不超过 ' +
                      str(current_app.\
                          config['ZENITH_VALID_THUMBNAIL_SIZE'] // 1024) +
                      'KB！')
                os.remove(filepath)
                os.rmdir(randomBasePath)
                return redirect(url_for('main.edit_profile',
                                        _external=True))
            else:
                # 验证通过，更新头像
                for _suffix in current_app.config['ZENITH_VALID_THUMBNAIL']:
                    thumbnailPath = os.path.join(basedir,
                                'app/static/thumbnail/' +
                                str(current_user.uid) + _suffix)
                    if os.path.isfile(thumbnailPath):
                        # 之前存在头像则先删除
                        os.remove(thumbnailPath)
                        break

                # 拷贝新头像
                shutil.copy(
                    filepath,
                    os.path.join(basedir,
                        'app/static/thumbnail/' +
                        str(current_user.uid) + suffix)
                )
                # 删除缓存
                os.remove(filepath)
                os.rmdir(randomBasePath)
                current_user.avatar_hash = ':' + \
                    url_for('static',
                           filename = 'thumbnail/' +
                                str(current_user.uid) + suffix,
                           _external=True)

        current_user.nickname = form.nickname.data
        current_user.about_me = form.about_me.data
        db.session.add(current_user)
        db.session.commit()
        flash('您的资料已更新')
        return redirect(url_for('.user',
                                id=current_user.uid,
                                _external=True))
    form.nickname.data = current_user.nickname
    form.about_me.data = current_user.about_me
    return render_template('main/profile/edit_profile.html', form=form)

# ----------------------------------------------------------------------
# device 显示具体的设备信息
@main.route('/device/<int:id>', methods=['GET', 'POST'])
def device(id):
    device = Device.query.get_or_404(id)
    if device.owner != current_user:
        # 设备不属于当前用户则返回 403 错误
        abort(403)
    return render_template('main/device.html',
                           device=device)

# --------------------------------------------------------------------
# delete_device 为用户提供了删除设备界面的入口，用户需对自己的删除操作进行
# 确认后，方可产生一个一次性的 token，并使用此 token 跳转到 delete_devi-
# ce_confirm 入口执行删除操作。
@main.route('/delete-device/<int:id>', methods=['GET','POST'])
@login_required
def delete_device(id):
    device = Device.query.get_or_404(id)
    if current_user != device.owner:
        abort(403)
    flash('小心！删除操作不能撤回！')
    form = DeviceDeleteForm()
    if form.validate_on_submit():
        if current_user.verify_password(form.password.data):
            db.session.delete(device)
            flash('设备' + device.name + '已被删除！')
            return redirect(url_for('main.index'))
        else:
            flash('您输入的密码不正确！')
            return redirect(url_for('main.device',
                                    id = device.uid,
                                    _external=True))
    return render_template('main/devices/confirm_delete_device.html',
                           device = device,
                           form = form)

# -----------------------------------------------------------------------
# edit_device 函数为用户编辑设备信息（重命名、选择类型、修改描述）界面提供了入口
@main.route('/edit-file/<int:id>', methods=['GET','POST'])
@login_required
def edit_device(id):
    device = Device.query.get_or_404(id)
    if current_user != device.owner:
        abort(403)
    form = DeviceEditForm()
    if form.validate_on_submit():
        device.name = form.name.data
        if form.name.data == '' or \
            form.name.data is None:
            device.name = '设备名称未指定'
        device.about = form.about.data
        device.type = form.type.data
    form.about.data = device.about
    form.name.data = device.name
    form.type.data = device.type
    return render_template('main/devices/edit_device.html',
                           device = device,
                           form = form)

# ------------------------------------------------------------------------
# newdevice 为用户创建设备提供了入口
@main.route('/new_device/', methods=['GET', 'POST'])
@login_required
def newdevice():
    form = NewDeviceForm()
    if form.validate_on_submit():
        d = deviceTable[form.type.data]()
        d.name = form.name.data
        d.about = form.about.data
        db.session.add(d)
    return render_template('main/devices/new_device.html',
                           form = form)

# ------------------------------------------------------------------------
# 设备更新信息路由
@main.route('/upload_status/', methods=['POST'])
def update_status():
    code = request.form.get('code')
    token = request.form.get('token')
    type = request.form.get('type')
    status = request.form.get('status')
    # print(code, token, type, status)
    if code is None or token is None or \
        type is None or status is None:
        return 'fail'
    deviceType = deviceTable.get(type)
    if deviceType is None:
        return 'fail'
    device = deviceType.query.filter_by(code=code).first()
    if device is None:
        return 'fail'
    if device.owner.verify_token(token):
        r = Record(device=device,
                   status=status)
        device.updateStatus(status)
        return 'ok'


@ main.route('/reset_token/<token>', methods=['POST'])
@login_required
def reset_token(token):
    if current_user.reset_token(token):
        return redirect(url_for('main.user', id=current_user.uid))
    else:
        abort(403)

@main.route('/show_status/', methods=['POST'])
def show_status():
    token = request.form.get('request[token]')
    email = request.form.get('request[email]')
    code = request.form.get('request[code]')
    if token is None or email is None:
        return 'fail'
    user = User.query.filter_by(email=email).first()
    if user is None or not user.verify_token(token):
        return 'fail'
    if code is None:
        # 请求所有设备的状态
        returnList = []
        devices = user.devices.all()
        for device in devices:
            returnList.append({
                'code': device.code,
                'status': device.getStatus()
            })
        return jsonify({
            'list': returnList
        })
    else:
        device = Device.query.filter_by(code=code)
        if device.owner != user:
            return
        return jsonify({
            'code': device.code,
            'status': device.getStatus()
         })
    return 'fail'