'use strict';

/* Controllers */

var mediaControllers = angular.module('mediaControllers', []);

mediaControllers.factory('SharedData', function () {
  return {};
});

function get_cards($scope, $http, callback) {
  $http.get('/API/cards').success(function (data) {
    // We could fromat the data here so we can foreach over many data sources:
    // $scope.content.push({'heading': 'Cards', 'data': data});
    // This reduces flexibility though - can't handle cards differently from
    // bugs. Fine for name + url lists, not useful for other stuff.
    $scope.shared_data.cards = [];
    $scope.lanes = [];

    data.every(function (card) {
      if (card.hasOwnProperty('Board') && card.Board) {
        $scope.shared_data.board = card;
        for (var key in card.lanes) {
          if (card.lanes.hasOwnProperty(key)) {

            // We ignore In Progress and Done because they are parent lanes
            if (key !== "In Progress" && key !== "Done") {
              $scope.lanes.push(key);
            }
          }
        }
        return true;
      }

      // Real cards
      card.md = toMarkdown(card.Description);
      card.Description = marked(card.md);
      $scope.shared_data.cards.push(card);

      return true;
    });

    if(callback != undefined) {
      callback();
    }
  });
}

mediaControllers.controller('EditCtrl', ['$scope', '$routeParams', '$location', '$http', 'SharedData',
  function ($scope, $routeParams, $location, $http, SharedData) {
    $scope.shared_data = SharedData;

    $scope.editor = ace.edit("editor");
    $scope.editor.setTheme("ace/theme/chrome");
    $scope.editor.getSession().setMode("ace/mode/markdown");

    $scope.updateEditor = function() {
      $scope.cardIndex = 0;
      while($scope.shared_data.cards[$scope.cardIndex]._id != $routeParams.id) {
        $scope.cardIndex++;
      }

      $scope.editor.getSession().setValue(toMarkdown($scope.shared_data.cards[$scope.cardIndex].Description));
      $scope.editor.resize();
    };

    if (!$scope.shared_data.hasOwnProperty('cards')) {
      get_cards($scope, $http, $scope.updateEditor);
    } else {
      $scope.updateEditor();
    }

    $scope.saveCard = function() {
      $scope.shared_data.cards[$scope.cardIndex].Description = marked($scope.editor.getSession().getValue());
      $http.post("/API/updateCardDescription", $scope.shared_data.cards[$scope.cardIndex]);
      $location.path("/");
    };

    $scope.discardChanges = function() {
      $location.path("/");
    };
  }]);

mediaControllers.controller('ToolbarCtrl', ['$scope', '$http', '$interval', '$location', 'SharedData',
  function ($scope, $http, $interval, $location, SharedData) {
    $scope.shared_data = SharedData;
    $scope.socket = io();
    $scope.socket.on('update', function(msg) {
      $scope.update();
    });

    var process_success = function (data) {
      var juju_pull_reqs = data;

      juju_pull_reqs.every(function(currentValue, index, array){
        if(currentValue.user.login == "dooferlad") {
          $scope.pull_reqs.push(currentValue);
        }
        return true;
      })
    };

    $scope.pull_reqs = [];
    $http.get('http://api.github.com/repos/juju/juju/pulls').success(process_success);
    $http.get('http://api.github.com/repos/juju/names/pulls').success(process_success);
    $http.get('http://api.github.com/repos/juju/testing/pulls').success(process_success);

    // Update our github sources every 5 minutes. AngularJS re-draws the UI for us :-)
    var update_promise = $interval(function() {
      $scope.pull_reqs = [];
      $http.get('http://api.github.com/repos/juju/juju/pulls').success(process_success);
      $http.get('http://api.github.com/repos/juju/names/pulls').success(process_success);
      $http.get('http://api.github.com/repos/juju/testing/pulls').success(process_success);
    }, 5 * 60 * 1000);

    $scope.$on('$destroy', function(){
      if (angular.isDefined(promise)) {
        $interval.cancel(promise);
        update_promise = undefined;
      }
    });

    $scope.update = function() {
        $http.get('/API/cards').success(function (data) {
        // We could fromat the data here so we can foreach over many data sources:
        // $scope.content.push({'heading': 'Cards', 'data': data});
        // This reduces flexibility though - can't handle cards differently from
        // bugs. Fine for name + url lists, not useful for other stuff.
        $scope.shared_data.cards = [];
        $scope.lanes = [];

        data.every(function(card) {
          if (card.hasOwnProperty('Board') && card.Board) {
            $scope.shared_data.board = card;
            for (var key in card.lanes) {
              if (card.lanes.hasOwnProperty(key)) {

                // We ignore In Progress and Done because they are parent lanes
                if(key !== "In Progress" && key !== "Done") {
                  $scope.lanes.push(key);
                }
              }
            }
            return true;
          }

          // Real cards
          card.md = toMarkdown(card.Description);
          card.Description = marked(card.md);
          $scope.shared_data.cards.push(card);

          return true;
        });
      });

      $http.get('/API/bugs').success(function (data) {
        $scope.my_bugs = data;
      });

      /*$http.get('/API/watched_bugs').success(function (data) {
        $scope.watched_bugs = data;
      });*/

      $http.get('/API/review_requests').success(function (data) {
        $scope.review_requests = data;
      });

      $http.get('/API/watched_reviews').success(function (data) {
        $scope.watched_reviews = data;
      });

      $http.get('/API/ci_jobs').success(function (data) {
        $scope.ci_jobs = data;
      });

      $http.get('/API/calendar').success(function (data) {
        $scope.calendar = [];
        if(data === "") {
          return;
        }
        data.every(function(event){
          var d = new Date();
          event.starttime = Date.parse(event.Start);
          d.setTime(event.starttime);
          event.dtstart = d.toLocaleTimeString().slice(0,5);
          if (event.hangoutLink !== "" ) {
            event.url = event.HangoutLink;
          } else {
            event.url = event.HtmlLink;
          }
          $scope.calendar.push(event);
          return true;
        });
      });
    };

    /*$http.get('/API/cal').success(function (data) {
      //$scope.cal = data;
      $scope.cal = [];
      var now = Date.now()
      data.events.every(function(event){
        var t_diff = Date.parse(event.dtstart) - now;
        if(t_diff > 0 && t_diff < 1000*60*60*24*7) {
          var d = new Date();
          event.starttime = Date.parse(event.dtstart);
          d.setTime(event.starttime);
          event.dtstart = d.toString();
          d.setTime(Date.parse(event.dtend));
          event.dtend = d.toString();
          $scope.cal.push(event);
        }
        return true;
      });
    });*/

    $scope.ci_job_filter = function(job) {
      return job.mine === true
    };

    $scope.card_filter = function(card) {
      if(card.hasOwnProperty('Board') && card.Board){
        return false;
      }
      return card.LaneTitle != "Merged";
    };

    $scope.bug_filter = function(bug) {
      return !(bug.status == "Fix Committed" ||
               bug.status == "Fix Released")
    };

    $scope.bug_url_submit = function(bug_url) {
      console.log(bug_url);
    };

    $scope.bugLabelImportance = function(bug) {
      switch(bug.importance) {
        case "Undecided":
          return "";
        case "Critical":
          return "label-danger";
        case "High":
          return "label-warning";
        case "Medium":
          return "label-success";
        case "Low":
          return "label-primary";
        case "Wishlist":
          return "label-info";
      }
      return "";
    };

    $scope.bugLabelStatus = function(bug) {
      switch(bug.status) {
        case "Invalid":
        case "Won't Fix":
          return "";
        case "New":
          return "label-danger";
        case "Triaged":
          return "label-warning";
        case "Fix Committed":
        case "Fix Released":
          return "label-success";
        case "Opinion":
          return "label-primary";
        case "In Progress":
          return "label-info";
      }
      return "";
    };

    $scope.cardLaneLabel = function(card) {
      switch(card.LaneTitle) {
        case "Done":
        case "Archive":
        case "Backlog":
        case "Merged":
          return "";

        case "Review":
        case "Under Review":
        case "Landing":
          return "label-success";

        case "Investigating":
        case "ToDo":
        case "Iteration Backlog":
          return "label-warning";

        case "Actively Working":
        case "In Progress":
        case "Doing":
        case "Coding":
          return "label-info";
      }
      return "label-danger";
    };

    $scope.cardButtonClass = function(card) {
      switch(card.LaneTitle) {
        case "Done":
        case "Archive":
        case "Backlog":
          return "";
        case "Review":
          return "btn-success";
        case "Investigating":
        case "ToDo":
          return "btn-primary";
        case "Doing":
        case "Coding":
          return "btn-info";
      }
      return "btn-danger";
    };

    $scope.ciJobLabel = function (job) {
      switch(job.result) {
        case "SUCCESS":
          return "label-success";
        case "FAILURE":
          return "label-danger";
      }
      return "label-primary";
    };

    $scope.taskUpdate = function(card, task, laneTitle) {
      task.LaneTitle = laneTitle;
      $http.post("/API/cards", {url: task.moveUrl + card.TaskLanes[laneTitle] + "/position/0"});
    };

    $scope.cardUpdate = function(card, laneTitle) {
      card.LaneTitle = laneTitle;
      var urlValue = card.moveUrl + $scope.shared_data.board.lanes[laneTitle] + "/position/0";
      console.log(urlValue);
      $http.post("/API/cards", {url: urlValue});
    };

    $scope.hasTasks = function(card){
      if(card.hasOwnProperty('Tasks')) {
        if(card.Tasks.length == 0){
          return false;
        }
      } else {
        return false;
      }
      return true;
    };

    $scope.hideTasks = function (card) {
      var hide = true;
      if (card.hasOwnProperty('hide')) {
        return card.hide;
      }
      card.Tasks.every(function (val, index, array) {
        if (val.LaneTitle !== "Done") {
          hide = false;
        }
        return true;
      });
      return hide;
    };

    $scope.editCard = function(card) {
      $location.path("/edit/" + card._id);
    };
  }]);

